# Obsidian の記法とプロパティ

ノートを書くときに必要な Obsidian 固有の記法をまとめたもの。標準の Markdown で書ける部分
（見出し・箇条書き・コードブロック等）は省略している。

## フロントマター（プロパティ）

ファイル先頭の `---` で囲まれた YAML。Obsidian 1.4 以降は「プロパティ」として UI に出る。

```markdown
---
tags:
  - project
  - 読書
created: 2026-08-24
due: 2026-09-01
status: doing
source: https://example.com/article
aliases:
  - 別名でも検索に引っかかる名前
cssclasses:
  - wide-table
---
```

型の扱いで気をつける点:

- **日付**は `2026-08-24` とクォート無しで書く。`'2026-08-24'` と書くとテキスト型になり、
  Dataview の日付比較やカレンダー系プラグインで扱えなくなる。
- **tags** は `#` を付けずに書く（`- project`）。`tags: [a, b]` のインライン記法も有効。
  タグに使えるのは英数字・`_`・`-`・`/` と日本語。空白は使えない（`-` か `_` にする）。
- **aliases** に別名を入れると `[[別名]]` でもそのノートにリンクできる。
- **リンクをプロパティに入れる**ときは `related: "[[ノート名]]"` のようにクォートする
  （`[` から始まる値は YAML では配列と解釈されるため）。

## リンクと埋め込み

| 記法 | 意味 |
|---|---|
| `[[ノート名]]` | 内部リンク |
| `[[ノート名\|表示名]]` | 表示名を変えたリンク |
| `[[ノート名#見出し]]` | 見出しへのリンク |
| `[[ノート名#^block-id]]` | ブロックへのリンク |
| `![[ノート名]]` | ノートの内容をその場に埋め込む（トランスクルージョン） |
| `![[画像.png]]` | 画像の埋め込み |
| `![[ノート名#見出し]]` | 見出し配下だけを埋め込む |

ブロック ID は、参照したい行末に `^block-id` と書いて付ける。

未作成のノートへのリンク（Obsidian では薄い色で表示される）は壊れているわけではなく、
「これから書く予定」を意味する使い方もある。リンク切れを報告するときはこの違いに触れる。

## タグ

本文中では `#タグ` と書く。`#親/子` で階層タグになる。
`#2026` のような数字だけのタグは Obsidian では無効（見出し記法と紛れるため）。
URL の `#anchor` はタグではない。

## タスク

```markdown
- [ ] 未完了のタスク
- [x] 完了したタスク ✅ 2026-08-24
- [ ] 期限つき 📅 2026-09-01
- [/] 進行中（テーマやプラグイン依存の拡張ステータス）
```

`- [x]` と絵文字による日付表記は Tasks プラグインの記法。プラグインが無くても、素の Markdown
チェックボックスとしてそのまま機能する。

## コールアウト

```markdown
> [!note] 補足
> 本文。

> [!warning]- 折りたたみ（- で閉じた状態、+ で開いた状態）
> クリックで開く。
```

使える種類: `note` `abstract` `info` `todo` `tip` `success` `question` `warning` `failure`
`danger` `bug` `example` `quote`。

## Dataview（プラグイン）

Dataview プラグインが入っていれば、フロントマターを使った動的な一覧が作れる。
**入っていない環境ではコードブロックがそのまま表示される**ので、Dataview に依存した
ノートを作るときは、静的な一覧も併記しておくと安全。

````markdown
```dataview
TABLE status AS "状態", due AS "期限"
FROM "Projects"
WHERE status != "done"
SORT due ASC
```

```dataview
LIST
FROM #読書 AND -"Templates"
WHERE created >= date(2026-01-01)
```
````

インラインフィールドは `キー:: 値` と書くと、フロントマターに入れなくても Dataview から参照できる。

## テンプレート

Templates フォルダのノートに `{{title}}` `{{date}}` `{{time}}` `{{date:YYYY-MM-DD}}` を書いておくと、
Obsidian のテンプレート機能で展開される。`scripts/vault.py new --template` も同じ置換に対応している。

## デイリーノート

設定は `.obsidian/daily-notes.json` にある（`format` / `folder` / `template`）。
`format` は moment.js 形式（`YYYY-MM-DD`、`YYYY/MM/YYYY-MM-DD` など）。
`scripts/vault.py daily` はこの設定を読んでパスを解決するので、手で組み立てない。

## Vault のフォルダ構成でよくある流儀

Vault ごとに流儀が違うので、勝手に新しい構成を持ち込まず、既存に合わせるのが原則。

- **PARA**: `Projects` / `Areas` / `Resources` / `Archive`
- **Zettelkasten**: `Inbox` / `Permanent` / `Literature` にノートを ID 付きで置く
- **日付ベース**: `Daily` / `Weekly` にすべて時系列で置く
- **MOC 方式**: フォルダは浅くし、`MOC - トピック名` という目次ノートからリンクで辿る

`scripts/vault.py info` のフォルダ一覧とタグ一覧を見れば、どの流儀に近いかは大体わかる。
