#!/usr/bin/env python3
"""hundred_skills_to_obsidian.py — 100スキルの進捗を Obsidian Vault のノート群に書き出す。

hundred-skill-tracker スキルが管理する `100-skills-progress.md` を読み込み、Obsidian 側に

    <出力フォルダ>/100スキル ダッシュボード.md   … 全体の進捗・ストリーク・次にやること
    <出力フォルダ>/フォルダ/01_AI活用・自動化.md  … フォルダごとの達成率と10項目
    <出力フォルダ>/スキル/01-02 ノーコード自動化….md … 1スキル1ノート（学びメモを書く場所）

を生成する。progress.md は「正」であり、このスクリプトは読むだけで書き換えない。

何度実行しても安全:
  各ノートの自動生成部分は <!-- hundred-skills:begin --> と <!-- hundred-skills:end --> で
  囲まれており、同期のたびにそのブロックとフロントマターの管理キーだけを更新する。
  ユーザーがブロックの外に書いた学びメモは決して消さない。

使い方:
    python3 hundred_skills_to_obsidian.py <progress.mdのパス> --vault <Vaultのパス> [options]

オプション:
    --folder NAME     出力先フォルダ（既定: 100スキル）
    --no-skill-notes  1スキル1ノートを作らず、ダッシュボードとフォルダノートだけにする
    --dry-run         書き込まずに、何が作成/更新されるかだけ表示する
    --json            結果を JSON で出力
"""

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault import (  # noqa: E402  同じフォルダの vault.py を再利用する
    compose,
    detect_vault,
    read_text,
    safe_filename,
    split_frontmatter,
    write_atomic,
)

FOLDER_RE = re.compile(r"^##\s+(.+?)\s*$")
ITEM_RE = re.compile(r"^- \[( |x|X)\]\s*(\d+)\.\s*(.+?)\s*(?:\((\d{4}-\d{2}-\d{2})\))?\s*$")
BEGIN = "<!-- hundred-skills:begin 自動生成ここから（このブロックは同期のたびに上書きされます） -->"
END = "<!-- hundred-skills:end 自動生成ここまで。以下に自由にメモを書けます -->"
BLOCK_RE = re.compile(
    re.escape(BEGIN).replace(r"\ ", " ") + r".*?" + re.escape(END).replace(r"\ ", " "),
    re.DOTALL,
)
MANAGED_KEYS = ("type", "スキル番号", "フォルダ", "フォルダ番号", "状態", "完了日", "tags")
DASHBOARD_TITLE = "100スキル ダッシュボード"


# --------------------------------------------------------------------------
# progress.md の解析と集計
# --------------------------------------------------------------------------
def parse_progress(path):
    folders, current = [], None
    for raw in read_text(path).splitlines():
        line = raw.rstrip()
        folder_match = FOLDER_RE.match(line)
        if folder_match:
            current = {"name": folder_match.group(1), "items": []}
            folders.append(current)
            continue
        item_match = ITEM_RE.match(line)
        if item_match and current is not None:
            checked, number, title, done_date = item_match.groups()
            current["items"].append(
                {
                    "number": int(number),
                    "title": title,
                    "done": checked.lower() == "x",
                    "date": done_date,
                }
            )
    return [f for f in folders if f["items"]]


def compute_streak(dates):
    if not dates:
        return 0, None
    days = sorted({date.fromisoformat(d) for d in dates}, reverse=True)
    most_recent = days[0]
    if (date.today() - most_recent).days > 1:
        return 0, most_recent.isoformat()
    streak, expected = 1, most_recent - timedelta(days=1)
    for day in days[1:]:
        if day == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif day < expected:
            break
    return streak, most_recent.isoformat()


def summarize(folders):
    all_dates, recent, folder_stats = [], [], []
    done_total = total = 0
    next_default = None

    for folder in folders:
        done = sum(1 for item in folder["items"] if item["done"])
        done_total += done
        total += len(folder["items"])
        next_incomplete = next((i for i in folder["items"] if not i["done"]), None)
        if next_default is None and next_incomplete:
            next_default = {"folder": folder["name"], **next_incomplete}
        for item in folder["items"]:
            if item["done"] and item["date"]:
                all_dates.append(item["date"])
                recent.append({**item, "folder": folder["name"]})
        folder_stats.append(
            {
                "name": folder["name"],
                "done": done,
                "total": len(folder["items"]),
                "pct": round(100 * done / len(folder["items"]), 1),
                "next_incomplete": next_incomplete,
                "items": folder["items"],
            }
        )

    streak, last_date = compute_streak(all_dates)
    recent.sort(key=lambda x: x["date"], reverse=True)
    return {
        "overall": {
            "done": done_total,
            "total": total,
            "pct": round(100 * done_total / total, 1) if total else 0.0,
        },
        "folders": folder_stats,
        "streak_days": streak,
        "last_completion_date": last_date,
        "next_default": next_default,
        "recent_completions": recent[:10],
    }


def cell(text):
    """Markdown テーブルのセルに入れる文字列（| は表を壊すのでエスケープする）。"""
    return str(text).replace("|", "\\|")


def bar(pct, width=20):
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


# --------------------------------------------------------------------------
# ノート名
# --------------------------------------------------------------------------
def folder_number(name):
    match = re.match(r"^(\d+)", name)
    return match.group(1) if match else "00"


def skill_note_title(folder_name, item):
    return f"{folder_number(folder_name)}-{item['number']:02d} {item['title']}"


def link(title):
    """ファイル名に使えない文字を置換した実際のノート名でリンクする。"""
    return f"[[{safe_filename(title)[:-3]}]]"


# --------------------------------------------------------------------------
# ノートの書き出し（管理ブロックだけ差し替える）
# --------------------------------------------------------------------------
def upsert_note(path, managed_front, managed_block, initial_tail, results, dry_run):
    """既存ノートがあれば管理部分だけ更新し、無ければ新規作成する。"""
    exists = path.exists()
    if exists:
        front, body, _ = split_frontmatter(read_text(path))
        if BLOCK_RE.search(body):
            new_body = BLOCK_RE.sub(lambda _: managed_block, body, count=1)
        else:
            # 既存ノートに管理ブロックが無い場合は、本文を残したまま先頭に足す
            new_body = f"{managed_block}\n\n{body.lstrip()}"
    else:
        front = {}
        new_body = f"{managed_block}\n\n{initial_tail}"

    merged = dict(front)
    merged.update(managed_front)
    ordered = {k: merged[k] for k in MANAGED_KEYS if k in merged}
    ordered.update({k: v for k, v in merged.items() if k not in MANAGED_KEYS})

    text = compose(ordered, new_body if new_body.endswith("\n") else new_body + "\n")
    action = "更新" if exists else "作成"
    if not exists or read_text(path) != text:
        if not dry_run:
            write_atomic(path, text)
        results.append({"action": action, "note": str(path)})
    else:
        results.append({"action": "変更なし", "note": str(path)})


def skill_note_block(folder, item, out_folder):
    status = "✅ 完了" if item["done"] else "⬜ 未着手"
    lines = [
        BEGIN,
        f"# {item['title']}",
        "",
        f"- 状態: **{status}**" + (f"（{item['date']} 完了）" if item["done"] and item["date"] else ""),
        f"- フォルダ: {link(folder['name'])}",
        f"- ダッシュボード: {link(DASHBOARD_TITLE)}",
        "",
        END,
    ]
    return "\n".join(lines)


def folder_note_block(folder, out_folder, with_skill_notes):
    lines = [
        BEGIN,
        f"# {folder['name']}",
        "",
        f"`{bar(folder['pct'])}` **{folder['done']}/{folder['total']}**（{folder['pct']}%）",
        "",
        "## スキル一覧",
        "",
    ]
    for item in folder["items"]:
        mark = "x" if item["done"] else " "
        label = link(skill_note_title(folder["name"], item)) if with_skill_notes else item["title"]
        suffix = f" （{item['date']}）" if item["done"] and item["date"] else ""
        lines.append(f"- [{mark}] {item['number']}. {label}{suffix}")
    lines += ["", f"← {link(DASHBOARD_TITLE)}", "", END]
    return "\n".join(lines)


def dashboard_block(stats, out_folder, with_skill_notes):
    overall = stats["overall"]
    lines = [
        BEGIN,
        "# 100スキル ダッシュボード",
        "",
        f"`{bar(overall['pct'], 30)}` **{overall['done']} / {overall['total']}**（{overall['pct']}%）",
        "",
    ]
    if stats["streak_days"] > 0:
        lines.append(f"🔥 **{stats['streak_days']}日連続**で学習中（最終完了日: {stats['last_completion_date']}）")
    elif stats["last_completion_date"]:
        lines.append(f"最終完了日: {stats['last_completion_date']}。少し間が空いています。")
    else:
        lines.append("まだ完了記録がありません。ここが出発点です。")

    lines += ["", "## フォルダ別の達成率", "", "| フォルダ | 進捗 | 達成率 | 次の1つ |", "|---|---|---|---|"]
    for folder in stats["folders"]:
        nxt = folder["next_incomplete"]
        next_label = cell(f"{nxt['number']}. {nxt['title']}") if nxt else "🎉 コンプリート"
        lines.append(
            f"| {cell(link(folder['name']))} | `{bar(folder['pct'], 10)}` {folder['done']}/{folder['total']} "
            f"| {folder['pct']}% | {next_label} |"
        )

    nxt = stats["next_default"]
    lines += ["", "## 次にやること", ""]
    if nxt:
        target = link(skill_note_title(nxt["folder"], nxt)) if with_skill_notes else nxt["title"]
        lines.append(f"- {target} — {nxt['folder']} の {nxt['number']}番目")
    else:
        lines.append("- 100スキルすべて完了しています 🎉")

    lines += ["", "## 直近の完了", ""]
    if stats["recent_completions"]:
        for item in stats["recent_completions"]:
            label = link(skill_note_title(item["folder"], item)) if with_skill_notes else item["title"]
            lines.append(f"- {item['date']} — {label}")
    else:
        lines.append("- （まだありません）")

    if with_skill_notes:
        lines += [
            "",
            "## 未完了スキル（Dataview プラグインを入れている場合のみ表示されます）",
            "",
            "```dataview",
            "TABLE フォルダ AS \"フォルダ\", スキル番号 AS \"番号\"",
            f'FROM "{out_folder}/スキル"',
            'WHERE 状態 = "未完了"',
            "SORT フォルダ番号 ASC, スキル番号 ASC",
            "LIMIT 20",
            "```",
            "",
            "## 完了スキルの履歴（同上）",
            "",
            "```dataview",
            "TABLE 完了日 AS \"完了日\", フォルダ AS \"フォルダ\"",
            f'FROM "{out_folder}/スキル"',
            'WHERE 状態 = "完了"',
            "SORT 完了日 DESC",
            "```",
        ]
    lines += ["", END]
    return "\n".join(lines)


# --------------------------------------------------------------------------
def sync(progress_path, vault_root, out_folder, with_skill_notes, dry_run):
    folders = parse_progress(progress_path)
    if not folders:
        raise SystemExit(
            f"error: 進捗ファイルから項目を読み取れませんでした: {progress_path}\n"
            "       `## フォルダ名` と `- [ ] 1. スキル名` の形式か確認してください。"
        )
    stats = summarize(folders)
    base = vault_root / out_folder
    results = []

    upsert_note(
        base / safe_filename(DASHBOARD_TITLE),
        {"type": "100スキル/ダッシュボード", "tags": ["100スキル"]},
        dashboard_block(stats, out_folder, with_skill_notes),
        "## ふりかえりメモ\n\n",
        results,
        dry_run,
    )

    for folder in stats["folders"]:
        upsert_note(
            base / "フォルダ" / safe_filename(folder["name"]),
            {
                "type": "100スキル/フォルダ",
                "フォルダ番号": folder_number(folder["name"]),
                "達成率": folder["pct"],
                "tags": ["100スキル", f"100スキル/{folder_number(folder['name'])}"],
            },
            folder_note_block(folder, out_folder, with_skill_notes),
            "## このフォルダのメモ\n\n",
            results,
            dry_run,
        )

        if not with_skill_notes:
            continue
        for item in folder["items"]:
            managed_front = {
                "type": "100スキル/スキル",
                "スキル番号": item["number"],
                "フォルダ": folder["name"],
                "フォルダ番号": folder_number(folder["name"]),
                "状態": "完了" if item["done"] else "未完了",
                "tags": ["100スキル", "100スキル/完了" if item["done"] else "100スキル/未完了"],
            }
            if item["done"] and item["date"]:
                managed_front["完了日"] = item["date"]
            upsert_note(
                base / "スキル" / safe_filename(skill_note_title(folder["name"], item)),
                managed_front,
                skill_note_block(folder, item, out_folder),
                "## 学んだこと\n\n\n## 実際にやったこと\n\n\n## 次に試すこと\n\n",
                results,
                dry_run,
            )

    return stats, results


def main():
    parser = argparse.ArgumentParser(description="100スキルの進捗を Obsidian に書き出す")
    parser.add_argument("progress", help="100-skills-progress.md のパス")
    parser.add_argument("--vault", help="Vault ルート（省略時は自動検出）")
    parser.add_argument("--folder", default="100スキル", help="Vault 内の出力先フォルダ")
    parser.add_argument("--no-skill-notes", action="store_true", help="1スキル1ノートを作らない")
    parser.add_argument("--dry-run", action="store_true", help="書き込まずに結果だけ表示")
    parser.add_argument("--json", action="store_true", help="JSON で出力")
    args = parser.parse_args()

    progress_path = Path(args.progress).expanduser()
    if not progress_path.is_file():
        raise SystemExit(f"error: 進捗ファイルが見つかりません: {progress_path}")

    vault_root = Path(args.vault).expanduser().resolve() if args.vault else detect_vault()
    if vault_root is None or not vault_root.is_dir():
        raise SystemExit("error: Vault が見つかりません。--vault で Vault のパスを指定してください。")

    stats, results = sync(
        progress_path, vault_root, args.folder.strip("/"), not args.no_skill_notes, args.dry_run
    )
    counts = {}
    for result in results:
        counts[result["action"]] = counts.get(result["action"], 0) + 1

    payload = {
        "vault": str(vault_root),
        "folder": args.folder,
        "dry_run": args.dry_run,
        "overall": stats["overall"],
        "streak_days": stats["streak_days"],
        "next_default": stats["next_default"],
        "counts": counts,
        "notes": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    prefix = "[dry-run] " if args.dry_run else ""
    summary = " / ".join(f"{action} {count}件" for action, count in sorted(counts.items()))
    print(f"{prefix}{vault_root / args.folder} に同期しました: {summary}")
    print(f"全体進捗: {stats['overall']['done']}/{stats['overall']['total']}（{stats['overall']['pct']}%）"
          f" / 連続学習: {stats['streak_days']}日")


if __name__ == "__main__":
    main()
