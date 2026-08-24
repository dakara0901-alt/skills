---
name: obsidian
description: >
  Obsidian の Vault（ローカルにある Markdown ノートのフォルダ）と連携して、ノートの検索・読み書き・
  整理を行うスキル。ノートの新規作成、既存ノートへの追記、YAML フロントマター（プロパティ）の更新、
  [[ウィキリンク]] や #タグ の整理、バックリンク・リンク切れ・孤立ノートの点検、デイリーノートの作成、
  MOC（目次ノート）づくりに使う。さらに hundred-skill-tracker が管理する 100-skills-progress.md を
  Obsidian のダッシュボード＋フォルダノート＋1スキル1ノートとして書き出す同期にも使う。
  ユーザーが「Obsidian」「オブシディアン」「Vault」「ボルト」「デイリーノート」「Zettelkasten」
  「第二の脳」「ノートに残して」「Vault に保存して」「Dataview」「100スキルの進捗を Obsidian に出して」
  などと言ったとき、あるいは .obsidian フォルダを含むディレクトリを扱うときは、このスキルを使うこと。
  Use for any Obsidian vault work: searching, creating and updating notes, frontmatter properties,
  wikilinks, tags, backlinks, daily notes, MOCs, and syncing the 100-skill tracker into a vault.
---

# Obsidian 連携

Obsidian の Vault は「`.obsidian` フォルダを含むただのローカルフォルダ」であり、ノートは普通の
Markdown ファイル。だから特別な API は要らず、ファイル操作でそのまま読み書きできる。ただし
「どのノートか一意に決める」「フロントマターを壊さず更新する」「リンク切れや孤立ノートを見つける」
といった Obsidian 固有の作業は手作業だと事故りやすいので、`scripts/vault.py` に任せる。

## 1. 最初に必ず Vault の場所を確定する

作業を始める前に、必ずどの Vault を触るのかを確定させる。順番はこう:

1. ユーザーがパスを言っていれば、それを使う。
2. 言っていなければ自動検出を試す:
   ```bash
   python3 scripts/vault.py detect            # カレントディレクトリから上に .obsidian を探す
   python3 scripts/vault.py detect ~/Documents
   ```
3. 見つからなければ**推測せずに聞く**。よくある場所は `~/Documents/<Vault名>`、
   `~/Obsidian/<Vault名>`、iCloud なら
   `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<Vault名>`。

Vault が決まったら、以降のコマンドはすべて `--vault <パス>` を付けて実行する。
最初に一度 `info` を見ておくと、フォルダ構成やタグの流儀（そのユーザーがどんな分類をしているか）が
分かって、後で作るノートを既存の体系に馴染ませやすい。

```bash
python3 scripts/vault.py --vault "$VAULT" info
```

**リモート環境で Vault が存在しない場合**: このセッションがユーザーのマシンではなくクラウド上で
動いているときは、ユーザーの Vault はここには無い。その場合は Vault を勝手に新規作成せず、
「Vault はこの環境から見えないので、生成したノートをファイルとして渡す／Vault のパスを教えてもらう」
のどちらにするかを確認する。

## 2. スクリプトでできること

`scripts/vault.py <コマンド> --vault <パス>` の形で使う。`--json` を付けると集計しやすい JSON で返る。

| コマンド | 用途 |
|---|---|
| `detect [起点]` | Vault ルート（`.obsidian` のある場所）を探す |
| `info` | ノート数・フォルダ構成・よく使われているタグ |
| `ls [--folder F]` | ノート一覧 |
| `search "語" [--tag T] [--folder F] [--regex] [--context 2]` | 全文検索（本文の行番号付き） |
| `read ノート [--section "## 見出し"]` | ノートを読む。見出し配下だけの抜き出しも可 |
| `new "タイトル" [--folder F] [--tag T] [--set key=value] [--body-file -]` | 新規作成（既存は上書きしない） |
| `append ノート [--section "## 見出し"] [--body-file -]` | 末尾または特定の見出し配下に追記 |
| `props ノート [--set k=v] [--unset k] [--add-tag t] [--remove-tag t]` | フロントマターの表示・更新 |
| `links ノート` | 発リンク・被リンク（バックリンク）・リンク切れ |
| `tags` / `orphans` / `broken` | タグ集計 / 孤立ノート / リンク切れ一覧 |
| `daily [--date YYYY-MM-DD] [--create]` | Vault の設定に従ってデイリーノートを解決・作成 |
| `uri ノート` | `obsidian://open?...` を出力（ユーザーがすぐ開ける） |

ノートは「パス」でも「ノート名」でも指定できる（`read プロジェクトA` でも `read Notes/プロジェクトA.md`
でもよい）。同名ノートが複数あるときはエラーで候補を出すので、パスで指定し直す。

長い本文を渡すときは、シェルのクォート事故を避けるためヒアドキュメント＋`--body-file -` を使う:

```bash
python3 scripts/vault.py --vault "$VAULT" new "会議メモ 2026-08-24" --folder "Meetings" \
  --tag meeting --set "status=draft" --body-file - <<'NOTE'
# 会議メモ

- 参加者: [[田中さん]]
NOTE
```

## 3. ノートを書くときの型

Obsidian らしいノートにするために、少なくとも次を意識する。詳しい記法は
`references/obsidian-syntax.md` を読む（フロントマターの型、コールアウト、埋め込み、Dataview など）。

- **フロントマター（プロパティ）**: `tags` と、日付は `YYYY-MM-DD` で入れる。Obsidian が
  date 型として扱えるよう、クォートせずに書く（スクリプトはそう出力する）。
- **リンク**: 関連ノートは `[[ノート名]]` で必ずつなぐ。Obsidian は孤立ノートが増えると価値が落ちる。
  リンク先が存在しない場合は、意図的な「未作成リンク」なのかリンク切れなのかを区別して伝える。
- **タグ**: 新しいタグを勝手に増やさない。まず `tags` コマンドで既存のタグを見て、そこに合わせる。
- **ファイル名**: `/ \ : * ? " < > | # ^ [ ]` はファイル名に使えないのでスクリプトが全角に置換する。
  日付を含めるなら `YYYY-MM-DD` を先頭に置くと並び順が安定する。

## 4. 壊さないためのルール

ユーザーの Vault は本人の思考の蓄積そのもの。次を必ず守る。

- **既存ノートを上書きしない**。内容を足すときは `append`、プロパティだけ変えるときは `props`。
  `new --force` は、ユーザーが明示的に「作り直して」と言ったときだけ。
- **一括変更の前に必ず確認を取る**。複数ノートのリネーム、タグの付け替え、フォルダ移動などは
  対象件数を示してから実行する（リネームは `[[リンク]]` を張り替えないと壊れる点も伝える）。
- **`.obsidian/` を編集しない**。プラグイン設定やテーマはユーザーの領域。読むのは可。
- **削除しない**。不要と思っても、提案までにとどめる。
- フロントマターを書き換えると YAML のコメントは失われる。コメント付きのノートを更新するときは
  一言断る。

## 5. 100スキル進捗を Obsidian に書き出す

`hundred-skill-tracker` スキルが管理する `100-skills-progress.md` を、Obsidian で見られる形に
変換する。ユーザーが「100スキルの進捗を Obsidian に出して／同期して」と言ったときに使う。

```bash
python3 scripts/hundred_skills_to_obsidian.py <100-skills-progress.mdのパス> \
  --vault "$VAULT" [--folder "100スキル"] [--no-skill-notes] [--dry-run]
```

生成されるもの:

- `100スキル/100スキル ダッシュボード.md` — 全体の達成率・連続学習日数・フォルダ別の表・次にやること
- `100スキル/フォルダ/01_AI活用・自動化.md` — フォルダごとの達成率と10項目のチェックリスト
- `100スキル/スキル/01-03 AIエージェント構築….md` — 1スキル1ノート（学びメモを書き溜める場所）

**進捗の正は常に `100-skills-progress.md`**。このスクリプトは progress.md を読むだけで書き換えない。
完了の記録は今まで通り hundred-skill-tracker に任せ、記録が更新されたあとにこの同期を走らせる
（`--dry-run` で件数だけ先に見せると安心してもらえる）。各ノートの自動生成部分は
`<!-- hundred-skills:begin -->` 〜 `<!-- hundred-skills:end -->` で囲まれており、何度同期しても
ユーザーがその外に書いた学びメモは消えない。

詳しい構造・Dataview クエリ・運用の流れは `references/hundred-skills-sync.md` を読む。

## 6. よくある依頼と進め方

- **「今日の分をデイリーノートに書いて」** → `daily --create` でパスを確定 →`append` で追記。
  その日の内容は箇条書きにし、関連ノートに `[[ ]]` を張る。
- **「Vault を整理して」** → `orphans` と `broken` と `tags` を先に出し、現状を要約してから
  何をどう直すか提案する（勝手に直さない）。
- **「◯◯についてのノートをまとめて」** → `search` で関連ノートを集め、MOC（目次ノート）を新規作成し、
  各ノートへ `[[ ]]` でリンクする。元ノート側にも MOC へのリンクを足すかは確認してから。
- **「調べた内容を Obsidian に保存して」** → 出典 URL を `source` プロパティに入れ、要約を本文に、
  関連する既存ノートにリンクする。既存ノートの体系（フォルダとタグ）に合わせること。
