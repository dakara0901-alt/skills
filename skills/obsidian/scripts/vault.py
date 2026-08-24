#!/usr/bin/env python3
"""vault.py — Obsidian Vault（= .md ファイルの入ったフォルダ）を安全に読み書きする CLI。

Obsidian の Vault はただのローカルフォルダなので、Claude は普通のファイル操作で
読み書きできる。ただし「どのノートがどれか」「フロントマターを壊さず更新する」
「リンク切れや孤立ノートを見つける」といった Obsidian 固有の作業は手作業だと
間違えやすいので、そこだけをこのスクリプトに任せる。

使い方:
    python3 vault.py <command> [--vault PATH] [options]

コマンド:
    detect [START]          .obsidian のあるフォルダ（Vault ルート）を上に辿って探す
    info                    ノート数・タグ数・フォルダ構成などの概要
    ls                      ノート一覧（--folder / --limit）
    search QUERY            全文検索（--tag / --folder / --regex / --context）
    read NOTE               ノートを表示（--section で見出し配下だけ）
    new TITLE               ノートを新規作成（既存なら --force なしでは上書きしない）
    append NOTE             ノート末尾または --section 見出し配下に追記
    props NOTE              フロントマターの表示・更新（--set/--unset/--add-tag/--remove-tag）
    links NOTE              発リンクと被リンク（バックリンク）
    tags                    タグの出現回数ランキング
    orphans                 どこからもリンクされていないノート
    broken                  存在しないノートを指しているリンク
    daily                   デイリーノートのパスを解決（--date / --create）
    uri NOTE                obsidian://open?... の URI を出力

全コマンド共通:
    --vault PATH   Vault ルート。省略時はカレントディレクトリから上に探索する。
    --json         結果を JSON で出力（Claude が集計に使う場合はこちら）。
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - PyYAML が無い環境でも動くようにする
    yaml = None

SKIP_DIRS = {".obsidian", ".trash", ".git", ".smart-env", "node_modules", ".stfolder"}
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]\[|#^]+)(?:[#^][^\]\[|]*)?(?:\|([^\]\[]*))?\]\]")
MDLINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+\.md)(?:\s+\"[^\"]*\")?\)")
# Obsidian のインラインタグ。URL の #anchor や word#x を拾わないよう、直前が単語構成文字や
# / & = - の場合は除外する（日本語の句読点のあとは正しくタグとして扱う）。
INLINE_TAG_RE = re.compile(r"(?<![\w/&=#-])#([^\s#,.;:!?'\"()\[\]{}。、「」『』（）！？・…]+)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
ILLEGAL_FILENAME_CHARS = {
    "/": "／", "\\": "＼", ":": "：", "*": "＊", "?": "？", '"': "”",
    "<": "＜", ">": "＞", "|": "｜", "#": "＃", "^": "＾", "[": "［", "]": "］",
}


# --------------------------------------------------------------------------
# Vault の探索と走査
# --------------------------------------------------------------------------
def detect_vault(start=None):
    """start から親方向に .obsidian を探す。見つからなければ None。"""
    current = Path(start or os.getcwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".obsidian").is_dir():
            return candidate
    return None


def resolve_vault(args):
    if args.vault:
        root = Path(args.vault).expanduser().resolve()
        if not root.is_dir():
            fail(f"Vault が見つかりません: {root}")
        return root
    root = detect_vault()
    if root is None:
        fail(
            "Vault を自動検出できませんでした。--vault で Vault のパスを指定してください"
            "（Vault ルートには .obsidian フォルダがあります）。"
        )
    return root


def iter_notes(root):
    """Vault 内の .md ファイルを、設定用フォルダを除いて列挙する。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".obsidian"))
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                yield Path(dirpath) / name


def rel(root, path):
    return str(Path(path).resolve().relative_to(root)).replace(os.sep, "/")


def norm(text):
    """比較用の正規化（全角/半角・大文字小文字の揺れを吸収）。"""
    return unicodedata.normalize("NFKC", text).casefold()


# --------------------------------------------------------------------------
# フロントマター
# --------------------------------------------------------------------------
def split_frontmatter(text):
    """(frontmatter dict, body str, raw_frontmatter str|None) を返す。"""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text, None
    raw = match.group(1)
    body = text[match.end():]
    return parse_yaml(raw), body, raw


def parse_yaml(raw):
    if yaml is not None:
        try:
            data = yaml.safe_load(raw)
            return normalize_values(data) if isinstance(data, dict) else {}
        except Exception:
            return {}
    return _mini_yaml(raw)


def normalize_values(value):
    """YAML が date / datetime に変換した値を ISO 文字列に戻す（JSON 出力と再書き出しのため）。"""
    if isinstance(value, dict):
        return {k: normalize_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_values(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _mini_yaml(raw):
    """PyYAML が無い環境向けの最小パーサ（スカラーと単純なリストのみ）。"""
    data, key = {}, None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and line.lstrip().startswith("- ") and key:
            data.setdefault(key, [])
            if isinstance(data[key], list):
                data[key].append(_scalar(line.lstrip()[2:]))
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            data[key] = [] if value == "" else _scalar(value)
    return data


def _scalar(value):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_scalar(v) for v in inner.split(",")] if inner else []
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value in ("true", "false"):
        return value == "true"
    return value


ISO_QUOTED_RE = re.compile(r"^([ \t]*(?:-|[^:\n]+:)[ \t]*)'(\d{4}-\d{2}-\d{2})'[ \t]*$", re.MULTILINE)


class _IndentedDumper(yaml.SafeDumper if yaml is not None else object):
    """Obsidian が書くのと同じく、リストを 2 スペース字下げで出力する。"""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def dump_frontmatter(data):
    if not data:
        return ""
    if yaml is not None:
        dumped = yaml.dump(
            data, Dumper=_IndentedDumper, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
        # 'YYYY-MM-DD' のクォートを外して Obsidian の date プロパティとして認識させる
        dumped = ISO_QUOTED_RE.sub(r"\1\2", dumped)
    else:
        lines = []
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                lines.extend(f"  - {v}" for v in value)
            elif isinstance(value, bool):
                lines.append(f"{key}: {'true' if value else 'false'}")
            else:
                lines.append(f"{key}: {value}")
        dumped = "\n".join(lines) + "\n"
    return f"---\n{dumped}---\n"


def compose(front, body):
    head = dump_frontmatter(front)
    if head and not body.startswith("\n"):
        return head + body
    return head + body


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def read_text(path):
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# ノートの解決
# --------------------------------------------------------------------------
def resolve_note(root, name, must_exist=True):
    """パス・ファイル名・ノート名のいずれからでもノートを 1 つに解決する。"""
    candidate = (root / name).resolve()
    if candidate.is_file():
        return candidate
    if not name.lower().endswith(".md"):
        candidate = (root / (name + ".md")).resolve()
        if candidate.is_file():
            return candidate

    stem = norm(Path(name).stem)
    matches = [p for p in iter_notes(root) if norm(p.stem) == stem]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        listing = "\n".join(f"  - {rel(root, m)}" for m in matches)
        fail(f"'{name}' に一致するノートが複数あります。パスで指定してください:\n{listing}")
    if must_exist:
        fail(f"ノートが見つかりません: {name}")
    return None


def strip_code_blocks(text):
    """リンク/タグ抽出用に、コードブロックとインラインコードを取り除く。"""
    out, in_fence = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        out.append("" if in_fence else re.sub(r"`[^`]*`", "", line))
    return "\n".join(out)


def outgoing_links(root, path):
    """ノートから出ているリンク先（ノート名）の一覧。"""
    text = strip_code_blocks(read_text(path))
    targets = [m.group(2).strip() for m in WIKILINK_RE.finditer(text)]
    for m in MDLINK_RE.finditer(text):
        target = m.group(1)
        if "://" not in target:
            targets.append(Path(target.replace("%20", " ")).stem)
    seen, result = set(), []
    for target in targets:
        key = norm(Path(target).stem)
        if key and key not in seen:
            seen.add(key)
            result.append(target)
    return result


def note_tags(front, body):
    tags = set()
    raw = front.get("tags") or front.get("tag") or []
    if isinstance(raw, str):
        raw = [t for t in re.split(r"[,\s]+", raw) if t]
    if isinstance(raw, list):
        tags.update(str(t).lstrip("#") for t in raw if str(t).strip())
    for match in INLINE_TAG_RE.finditer(strip_code_blocks(body)):
        tag = match.group(1)
        if not tag.replace("/", "").replace("-", "").replace("_", "").isdigit():
            tags.add(tag)
    return sorted(tags)


def build_index(root):
    """Vault 全体を 1 回だけ走査して、リンク解決に必要な情報を集める。"""
    notes = {}
    for path in iter_notes(root):
        text = read_text(path)
        front, body, _ = split_frontmatter(text)
        relpath = rel(root, path)
        notes[relpath] = {
            "path": path,
            "rel": relpath,
            "stem": path.stem,
            "front": front,
            "body": body,
            "tags": note_tags(front, body),
            "links": outgoing_links(root, path),
        }
    by_stem = {}
    for info in notes.values():
        by_stem.setdefault(norm(info["stem"]), []).append(info["rel"])
    return notes, by_stem


def link_target_rel(by_stem, notes, target):
    """リンク文字列から実在ノートの相対パスを求める（無ければ None）。"""
    cleaned = target.strip().replace("\\", "/")
    if cleaned.lower().endswith(".md"):
        cleaned = cleaned[:-3]
    for candidate in (cleaned + ".md", cleaned):
        if candidate in notes:
            return candidate
    hits = by_stem.get(norm(Path(cleaned).name), [])
    return hits[0] if len(hits) >= 1 else None


# --------------------------------------------------------------------------
# 出力ヘルパ
# --------------------------------------------------------------------------
def fail(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def emit(args, payload, human):
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(human)


# --------------------------------------------------------------------------
# コマンド
# --------------------------------------------------------------------------
def cmd_detect(args):
    root = detect_vault(args.start)
    if root is None:
        emit(args, {"vault": None}, "Vault が見つかりませんでした（.obsidian フォルダなし）")
        sys.exit(2)
    emit(args, {"vault": str(root)}, str(root))


def count_attachments(root):
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        total += sum(1 for f in filenames if not f.lower().endswith(".md"))
    return total


def cmd_info(args):
    root = resolve_vault(args)
    notes, _ = build_index(root)
    folders, tag_counts = {}, {}
    for info in notes.values():
        parent = str(Path(info["rel"]).parent)
        folder = "(ルート)" if parent == "." else parent
        folders[folder] = folders.get(folder, 0) + 1
        for tag in info["tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    payload = {
        "vault": str(root),
        "notes": len(notes),
        "attachments": count_attachments(root),
        "folders": sorted(folders.items(), key=lambda kv: -kv[1]),
        "tags": sorted(tag_counts.items(), key=lambda kv: -kv[1])[:30],
    }
    lines = [f"Vault: {root}", f"ノート: {payload['notes']} / 添付など: {payload['attachments']}", "", "フォルダ:"]
    lines += [f"  {name}: {count}" for name, count in payload["folders"][:20]]
    lines += ["", "よく使われているタグ:"]
    lines += [f"  #{tag}: {count}" for tag, count in payload["tags"][:15]] or ["  (なし)"]
    emit(args, payload, "\n".join(lines))


def cmd_ls(args):
    root = resolve_vault(args)
    results = []
    for path in iter_notes(root):
        relpath = rel(root, path)
        if args.folder and not relpath.startswith(args.folder.strip("/") + "/"):
            continue
        results.append(relpath)
    results = results[: args.limit]
    emit(args, {"notes": results}, "\n".join(results) or "(該当なし)")


def cmd_search(args):
    root = resolve_vault(args)
    notes, _ = build_index(root)
    if args.regex:
        flags = 0 if args.case_sensitive else re.IGNORECASE
        pattern = re.compile(args.query, flags)
        matcher = lambda line: bool(pattern.search(line))  # noqa: E731
    else:
        needle = args.query if args.case_sensitive else norm(args.query)
        matcher = (lambda line: needle in line) if args.case_sensitive else (lambda line: needle in norm(line))

    results = []
    for info in notes.values():
        if args.folder and not info["rel"].startswith(args.folder.strip("/") + "/"):
            continue
        if args.tag and args.tag.lstrip("#") not in info["tags"]:
            continue
        lines = info["body"].splitlines()
        hits = []
        for i, line in enumerate(lines):
            if line.strip() and matcher(line):
                start, end = max(0, i - args.context), min(len(lines), i + args.context + 1)
                hits.append({"line": i + 1, "text": line.strip(), "context": lines[start:end]})
            if len(hits) >= 5:
                break
        if hits or (args.tag and not args.query):
            results.append({"note": info["rel"], "tags": info["tags"], "hits": hits})
        if len(results) >= args.limit:
            break

    human = []
    for result in results:
        human.append(f"## {result['note']}")
        human += [f"  {hit['line']}: {hit['text']}" for hit in result["hits"]]
    emit(args, {"query": args.query, "results": results}, "\n".join(human) or "(ヒットなし)")


def cmd_read(args):
    root = resolve_vault(args)
    path = resolve_note(root, args.note)
    text = read_text(path)
    front, body, _ = split_frontmatter(text)
    if args.section:
        body = extract_section(body, args.section)
        if body is None:
            fail(f"見出しが見つかりません: {args.section}")
    payload = {"note": rel(root, path), "frontmatter": front, "tags": note_tags(front, body), "body": body}
    emit(args, payload, body if args.section else text)


def extract_section(body, heading):
    """指定見出しから、同レベル以上の次の見出しまでを取り出す。"""
    wanted = norm(heading.lstrip("# ").strip())
    lines = body.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match and norm(match.group(2).strip()) == wanted:
            start, level = i, len(match.group(1))
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        match = re.match(r"^(#{1,6})\s+", lines[j])
        if match and len(match.group(1)) <= level:
            return "\n".join(lines[start:j]).rstrip() + "\n"
    return "\n".join(lines[start:]).rstrip() + "\n"


def safe_filename(title, max_len=110):
    name = "".join(ILLEGAL_FILENAME_CHARS.get(ch, ch) for ch in title).strip().strip(".")
    return (name[:max_len].rstrip() or "untitled") + ".md"


def parse_props(pairs):
    props = {}
    for pair in pairs or []:
        if "=" not in pair:
            fail(f"--set は key=value の形式で指定してください: {pair}")
        key, _, value = pair.partition("=")
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            props[key] = [v.strip() for v in inner.split(",") if v.strip()]
        else:
            props[key] = value
    return props


def read_body_arg(args):
    if args.body_file:
        return sys.stdin.read() if args.body_file == "-" else read_text(Path(args.body_file))
    return (args.body or "")


def cmd_new(args):
    root = resolve_vault(args)
    folder = root / (args.folder.strip("/") if args.folder else "")
    path = folder / safe_filename(args.title)
    if path.exists() and not args.force:
        fail(f"既に存在します: {rel(root, path)}（上書きするなら --force、追記なら append コマンド）")

    body = read_body_arg(args)
    if args.template:
        template_path = resolve_note(root, args.template)
        t_front, t_body, _ = split_frontmatter(read_text(template_path))
        body = expand_template(t_body, args.title) + ("\n" + body if body else "")
        base_front = t_front
    else:
        base_front = {}

    front = {"created": date.today().isoformat()}
    front.update(base_front)
    front.update(parse_props(args.set))
    if args.tag:
        existing = front.get("tags") or []
        if isinstance(existing, str):
            existing = [existing]
        front["tags"] = list(dict.fromkeys([*existing, *[t.lstrip("#") for t in args.tag]]))

    if not body.strip():
        body = f"# {args.title}\n\n"
    elif not body.endswith("\n"):
        body += "\n"

    write_atomic(path, compose(front, body))
    emit(args, {"note": rel(root, path), "path": str(path)}, f"作成しました: {rel(root, path)}")


def expand_template(text, title):
    now = datetime.now()
    replacements = {
        "{{title}}": title,
        "{{date}}": now.strftime("%Y-%m-%d"),
        "{{time}}": now.strftime("%H:%M"),
        "{{date:YYYY-MM-DD}}": now.strftime("%Y-%m-%d"),
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def cmd_append(args):
    root = resolve_vault(args)
    path = resolve_note(root, args.note, must_exist=not args.create)
    addition = read_body_arg(args).rstrip("\n")
    if not addition:
        fail("追記する内容が空です（--body か --body-file を指定してください）")

    if path is None:
        path = (root / (args.folder.strip("/") if args.folder else "")) / safe_filename(Path(args.note).stem)
        write_atomic(path, compose({"created": date.today().isoformat()}, f"# {Path(args.note).stem}\n\n"))

    front, body, _ = split_frontmatter(read_text(path))
    if args.section:
        section = extract_section(body, args.section)
        if section is None:
            body = body.rstrip("\n") + f"\n\n{args.section if args.section.startswith('#') else '## ' + args.section}\n\n{addition}\n"
        else:
            updated = section.rstrip("\n") + f"\n{addition}\n"
            body = body.replace(section.rstrip("\n"), updated.rstrip("\n"), 1)
    else:
        body = body.rstrip("\n") + f"\n\n{addition}\n"

    write_atomic(path, compose(front, body))
    emit(args, {"note": rel(root, path)}, f"追記しました: {rel(root, path)}")


def cmd_props(args):
    root = resolve_vault(args)
    path = resolve_note(root, args.note)
    front, body, _ = split_frontmatter(read_text(path))

    changed = bool(args.set or args.unset or args.add_tag or args.remove_tag)
    front.update(parse_props(args.set))
    for key in args.unset or []:
        front.pop(key, None)
    if args.add_tag or args.remove_tag:
        tags = front.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        tags = [str(t).lstrip("#") for t in tags]
        tags += [t.lstrip("#") for t in (args.add_tag or []) if t.lstrip("#") not in tags]
        tags = [t for t in tags if t not in {r.lstrip("#") for r in (args.remove_tag or [])}]
        front["tags"] = tags

    if changed:
        write_atomic(path, compose(front, body))
    payload = {"note": rel(root, path), "frontmatter": front}
    human = json.dumps(front, ensure_ascii=False, indent=2)
    emit(args, payload, (f"更新しました: {rel(root, path)}\n" if changed else "") + human)


def cmd_links(args):
    root = resolve_vault(args)
    notes, by_stem = build_index(root)
    path = resolve_note(root, args.note)
    target_rel = rel(root, path)

    outgoing, broken = [], []
    for link in notes[target_rel]["links"]:
        resolved = link_target_rel(by_stem, notes, link)
        (outgoing if resolved else broken).append(resolved or link)

    backlinks = []
    for info in notes.values():
        if info["rel"] == target_rel:
            continue
        for link in info["links"]:
            if link_target_rel(by_stem, notes, link) == target_rel:
                backlinks.append(info["rel"])
                break

    payload = {"note": target_rel, "outgoing": outgoing, "backlinks": sorted(backlinks), "broken": broken}
    human = [f"## {target_rel}", "発リンク:"]
    human += [f"  → {o}" for o in outgoing] or ["  (なし)"]
    human += ["被リンク:"]
    human += [f"  ← {b}" for b in sorted(backlinks)] or ["  (なし)"]
    if broken:
        human += ["リンク切れ:"] + [f"  ✗ {b}" for b in broken]
    emit(args, payload, "\n".join(human))


def cmd_tags(args):
    root = resolve_vault(args)
    notes, _ = build_index(root)
    counts = {}
    for info in notes.values():
        for tag in info["tags"]:
            counts.setdefault(tag, []).append(info["rel"])
    ranked = sorted(counts.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    payload = {"tags": [{"tag": t, "count": len(n), "notes": n[:20]} for t, n in ranked]}
    emit(args, payload, "\n".join(f"#{t}: {len(n)}" for t, n in ranked) or "(タグなし)")


def cmd_orphans(args):
    root = resolve_vault(args)
    notes, by_stem = build_index(root)
    linked = set()
    for info in notes.values():
        for link in info["links"]:
            resolved = link_target_rel(by_stem, notes, link)
            if resolved and resolved != info["rel"]:
                linked.add(resolved)
    orphans = sorted(r for r in notes if r not in linked)
    emit(args, {"orphans": orphans}, "\n".join(orphans) or "(孤立ノートなし)")


def cmd_broken(args):
    root = resolve_vault(args)
    notes, by_stem = build_index(root)
    broken = []
    for info in notes.values():
        for link in info["links"]:
            if link_target_rel(by_stem, notes, link) is None:
                broken.append({"note": info["rel"], "link": link})
    human = "\n".join(f"{b['note']} → [[{b['link']}]]" for b in broken)
    emit(args, {"broken": broken}, human or "(リンク切れなし)")


MOMENT_TOKENS = [
    ("YYYY", "%Y"), ("YY", "%y"), ("MMMM", "%B"), ("MMM", "%b"), ("MM", "%m"),
    ("DDDD", "%j"), ("dddd", "%A"), ("ddd", "%a"), ("DD", "%d"),
    ("HH", "%H"), ("mm", "%M"), ("ss", "%S"),
]


def moment_to_strftime(fmt):
    out, i = "", 0
    while i < len(fmt):
        for token, repl in MOMENT_TOKENS:
            if fmt.startswith(token, i):
                out += repl
                i += len(token)
                break
        else:
            out += fmt[i]
            i += 1
    return out


def cmd_daily(args):
    root = resolve_vault(args)
    config = {}
    config_path = root / ".obsidian" / "daily-notes.json"
    if config_path.is_file():
        try:
            config = json.loads(read_text(config_path))
        except json.JSONDecodeError:
            config = {}
    fmt = config.get("format") or "YYYY-MM-DD"
    folder = (config.get("folder") or "").strip("/")
    when = date.fromisoformat(args.date) if args.date else date.today()
    filename = when.strftime(moment_to_strftime(fmt)) + ".md"
    path = root / folder / filename if folder else root / filename

    created = False
    if args.create and not path.exists():
        body = f"# {when.isoformat()}\n\n"
        template = config.get("template")
        if template:
            template_path = resolve_note(root, template, must_exist=False)
            if template_path:
                _, t_body, _ = split_frontmatter(read_text(template_path))
                body = expand_template(t_body, when.isoformat())
        write_atomic(path, compose({"created": when.isoformat()}, body))
        created = True

    payload = {"note": rel(root, path) if path.exists() else str(path.relative_to(root)),
               "exists": path.exists(), "created": created, "format": fmt, "folder": folder}
    emit(args, payload, str(path))


def cmd_uri(args):
    from urllib.parse import quote
    root = resolve_vault(args)
    path = resolve_note(root, args.note)
    uri = f"obsidian://open?vault={quote(root.name)}&file={quote(rel(root, path)[:-3])}"
    emit(args, {"uri": uri}, uri)


# --------------------------------------------------------------------------
def build_parser():
    # --vault / --json はサブコマンドの前後どちらに書いてもよい。SUPPRESS にしておくと、
    # 指定していない側が指定済みの値を None で上書きしてしまう事故を防げる。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--vault", default=argparse.SUPPRESS, help="Vault ルート（省略時は自動検出）")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="JSON で出力")

    parser = argparse.ArgumentParser(description="Obsidian Vault を読み書きする CLI", parents=[common])
    parser.set_defaults(vault=None, json=False)
    sub = parser.add_subparsers(dest="command", required=True)
    _add = sub.add_parser

    def add_parser(name, **kwargs):
        kwargs.setdefault("parents", [common])
        return _add(name, **kwargs)

    sub.add_parser = add_parser

    p = sub.add_parser("detect", help="Vault ルートを探す")
    p.add_argument("start", nargs="?", help="探索の起点（省略時はカレントディレクトリ）")
    p.set_defaults(func=cmd_detect)

    sub.add_parser("info", help="Vault の概要").set_defaults(func=cmd_info)

    p = sub.add_parser("ls", help="ノート一覧")
    p.add_argument("--folder")
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(func=cmd_ls)

    p = sub.add_parser("search", help="全文検索")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--tag")
    p.add_argument("--folder")
    p.add_argument("--regex", action="store_true")
    p.add_argument("--case-sensitive", action="store_true")
    p.add_argument("--context", type=int, default=0)
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("read", help="ノートを読む")
    p.add_argument("note")
    p.add_argument("--section", help="この見出し配下だけを取り出す")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("new", help="ノートを新規作成")
    p.add_argument("title")
    p.add_argument("--folder")
    p.add_argument("--tag", action="append")
    p.add_argument("--set", action="append", help="フロントマター key=value")
    p.add_argument("--body")
    p.add_argument("--body-file", help="本文をファイルから読む（- で標準入力）")
    p.add_argument("--template", help="テンプレートノート名")
    p.add_argument("--force", action="store_true", help="既存ノートを上書き")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("append", help="ノートに追記")
    p.add_argument("note")
    p.add_argument("--section")
    p.add_argument("--body")
    p.add_argument("--body-file")
    p.add_argument("--folder")
    p.add_argument("--create", action="store_true", help="無ければ作る")
    p.set_defaults(func=cmd_append)

    p = sub.add_parser("props", help="フロントマターの表示・更新")
    p.add_argument("note")
    p.add_argument("--set", action="append")
    p.add_argument("--unset", action="append")
    p.add_argument("--add-tag", action="append")
    p.add_argument("--remove-tag", action="append")
    p.set_defaults(func=cmd_props)

    p = sub.add_parser("links", help="発リンクと被リンク")
    p.add_argument("note")
    p.set_defaults(func=cmd_links)

    sub.add_parser("tags", help="タグ一覧").set_defaults(func=cmd_tags)
    sub.add_parser("orphans", help="孤立ノート").set_defaults(func=cmd_orphans)
    sub.add_parser("broken", help="リンク切れ").set_defaults(func=cmd_broken)

    p = sub.add_parser("daily", help="デイリーノート")
    p.add_argument("--date", help="YYYY-MM-DD（省略時は今日）")
    p.add_argument("--create", action="store_true")
    p.set_defaults(func=cmd_daily)

    p = sub.add_parser("uri", help="obsidian:// URI を出力")
    p.add_argument("note")
    p.set_defaults(func=cmd_uri)
    return parser


def scan_common_options(argv):
    """argparse のサブコマンドは共通オプションを上書きしてしまうので、--vault / --json だけ
    argv 全体から先に拾っておく（サブコマンドの前に書いても後ろに書いても効くようにするため）。"""
    scanner = argparse.ArgumentParser(add_help=False)
    scanner.add_argument("--vault")
    scanner.add_argument("--json", action="store_true")
    known, _ = scanner.parse_known_args(argv)
    return known


def main():
    argv = sys.argv[1:]
    common = scan_common_options(argv)
    args = build_parser().parse_args(argv)
    args.vault = args.vault or common.vault
    args.json = args.json or common.json
    args.func(args)


if __name__ == "__main__":
    main()
