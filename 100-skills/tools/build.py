#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build.py — 100スキル・コレクションの派生物を再生成する。

**単一の情報源 (source of truth)** は各スキルの README:
    100-skills/<NN_カテゴリ>/<連番_スキル名>/README.md

このスクリプトはそれらを解析し、以下を再生成する:
    100-skills/README.md                … トップ（全体インデックス）
    100-skills/<NN_カテゴリ>/README.md    … カテゴリ index（×10）
    100-skills/index.html                … 検索・絞り込み付きブラウズ版
    100-skills/obsidian-vault/           … Obsidian Vault 一式

毎週の更新手順:
    1. 対象スキルの README を編集（ツール・リソースの最新化、新スキルの追加など）
    2. `python3 100-skills/tools/build.py` を実行して派生物を再生成
    3. 差分を確認してコミット

スキル数は 100 に固定していない（新スキルの追加・入替にも追従する）。
使い方: python3 build.py [--check]
    --check  書き込まず、各カテゴリの件数と総数だけ表示する
"""
import os
import re
import sys
import glob
import html

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, ".."))      # .../100-skills
VAULT = os.path.join(BASE, "obsidian-vault")
HOME = "🏆 使える最高のスキル100"

# カテゴリのメタ情報（絵文字・一言キャッチ・色相）。カテゴリ番号で引く。
CAT_META = {
    "01": ("🤖", "AIと自動化で作業をゼロに", 262),
    "02": ("✍️", "言葉で価値を伝え、売る", 24),
    "03": ("🎨", "一目で伝わるビジュアルを作る", 330),
    "04": ("📣", "見込み客を集める仕組み", 4),
    "05": ("🤝", "信頼を築き、成約に導く", 200),
    "06": ("💻", "作りたいものを自分で形にする", 222),
    "07": ("📊", "データで正しく判断する", 158),
    "08": ("💰", "お金の流れを味方につける", 42),
    "09": ("⚖️", "リスクから自分と事業を守る", 285),
    "10": ("🚀", "成果を出し続ける自己管理術", 174),
}

_SAFE_MAP = str.maketrans({"/": "／", "\\": "＼", ":": "：", "*": "＊",
                           "?": "？", '"': "”", "<": "＜", ">": "＞", "|": "｜"})


def esc(s):
    return html.escape(str(s))


def safe(t):
    return t.translate(_SAFE_MAP)


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# --------------------------------------------------------------------------
# 解析: スキル README を読む
# --------------------------------------------------------------------------
def parse_skill(md_path):
    with open(md_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    title_line = next(l for l in lines if l.startswith("# "))
    m = re.match(r"#\s+\S+\s+(\d+)\.\s+(.+)", title_line)
    if not m:  # 絵文字なしのフォールバック
        m = re.match(r"#\s+(\d+)\.\s+(.+)", title_line)
    seq, title = m.group(1), m.group(2).strip()
    overview = next((l[2:].strip() for l in lines if l.startswith("> ")
                     and "[!" not in l), "")
    if not overview:  # callout 形式 "> ..." の次行
        for i, l in enumerate(lines):
            if l.strip().startswith("> [!") and i + 1 < len(lines):
                nxt = lines[i + 1]
                if nxt.startswith("> "):
                    overview = nxt[2:].strip()
                    break

    def section(header):
        out, capture = [], False
        for l in lines:
            if l.startswith("## "):
                capture = header in l
                continue
            if capture:
                s = l.strip()
                if s.startswith("- "):
                    out.append(s[2:].strip())
                elif re.match(r"^\d+\.\s", s):
                    out.append(re.sub(r"^\d+\.\s*", "", s).strip())
        return out

    return {
        "seq": seq,
        "n": int(seq),
        "title": title,
        "overview": overview,
        "tools": section("世界最高峰のツール"),
        "steps": section("実践ステップ"),
        "resources": section("厳選リソース"),
    }


def collect():
    cats = []
    for cd in sorted(glob.glob(os.path.join(BASE, "[0-9][0-9]_*"))):
        base = os.path.basename(cd)
        num, name = base.split("_", 1)
        emoji, tagline, hue = CAT_META.get(num, ("📘", "", 200))
        skills = []
        for leaf in sorted(glob.glob(os.path.join(cd, "*", "README.md"))):
            sk = parse_skill(leaf)
            sk["leaf"] = os.path.basename(os.path.dirname(leaf))
            sk["cat_num"] = num
            sk["cat_name"] = name
            skills.append(sk)
        skills.sort(key=lambda s: s["n"])
        cats.append({"num": num, "name": name, "emoji": emoji,
                     "tagline": tagline, "hue": hue, "skills": skills})
    cats.sort(key=lambda c: c["num"])
    return cats


# --------------------------------------------------------------------------
# 再生成: カテゴリ README
# --------------------------------------------------------------------------
def build_category_readmes(cats):
    for c in cats:
        rows = "\n".join(
            f"| `{s['seq']}` | **[{s['title']}](./{s['leaf']}/README.md)** | {s['overview']} |"
            for s in c["skills"]
        )
        seqs = [s["seq"] for s in c["skills"]]
        rng = f"No.{seqs[0]}〜{seqs[-1]}" if seqs else "—"
        body = f"""<div align="center">

# {c['emoji']} {c['num']}_{c['name']}

**{c['tagline']}**

`{rng}` ｜ スキル{len(c['skills'])}個

</div>

---

| No. | スキル | 概要 |
|:--:|---|---|
{rows}

<br>

> 💡 各スキル名をクリックすると、**世界最高峰のツール・手法／実践ステップ／厳選リソース**をまとめた個別ページが開きます。

---
<div align="center">

[🏠 全体インデックスに戻る](../README.md)

</div>
"""
        write(os.path.join(BASE, f"{c['num']}_{c['name']}", "README.md"), body)


# --------------------------------------------------------------------------
# 再生成: トップ README
# --------------------------------------------------------------------------
def build_top_readme(cats):
    card_rows = []
    for c in cats:
        seqs = [s["seq"] for s in c["skills"]]
        rng = f"{seqs[0]}–{seqs[-1]}" if seqs else "—"
        card_rows.append(
            f"| {c['emoji']} | **[{c['num']}. {c['name']}](./{c['num']}_{c['name']}/README.md)**"
            f"<br>{c['tagline']} | `No.{rng}` |"
        )
    card_table = "\n".join(card_rows)

    details = []
    for c in cats:
        items = "\n".join(
            f"- **[{s['seq']}. {s['title']}](./{c['num']}_{c['name']}/{s['leaf']}/README.md)** — {s['overview']}"
            for s in c["skills"]
        )
        seqs = [s["seq"] for s in c["skills"]]
        details.append(
            f"<details>\n<summary><b>{c['emoji']} {c['num']}_{c['name']}</b>"
            f"（No.{seqs[0]}〜{seqs[-1]}）</summary>\n\n{items}\n\n</details>"
        )
    all_details = "\n\n".join(details)

    total = sum(len(c["skills"]) for c in cats)
    res_count = sum(len(s["resources"]) for c in cats for s in c["skills"])
    body = f"""<div align="center">

# 🏆 使える最高のスキル100

**世界中から集めた「一人で問題解決し、AIをレバレッジして稼ぐ」ための実用スキル集**

`{len(cats)}カテゴリ` ｜ `{total}スキル` ｜ `{total}フォルダ`

</div>

---

「1項目 = 1フォルダ」で計**{total}フォルダ**に分割。各フォルダの `README.md` に
**📌概要 / 🌍世界最高峰のツール・手法 / 🛠実践ステップ / 📚厳選リソース** を収録しています。

> 🔄 このコレクションは**毎週（月曜 朝9時 JST）自動で最新化**され、新しいスキル・ツールが追加されます。

## 📂 カテゴリ一覧

|  | 分野 | 収録スキル |
|:--:|---|:--:|
{card_table}

## 🗂 全スキル一覧（クリックで展開）

{all_details}

## 🧭 使い方

1. 上のカテゴリ一覧から気になる**分野フォルダ**を開く
2. 各スキルフォルダの `README.md` で**世界最高峰のツール**と**実践ステップ**を確認
3. **厳選リソース**で深掘りする
4. 進捗管理は `hundred-skill-tracker` スキルと併用 → フォルダ別の達成率・学習ストリークを記録できます

> ブラウザで見るなら [`index.html`](./index.html)（検索・絞り込み対応）、
> Obsidianで使うなら [`obsidian-vault/`](./obsidian-vault) を保管庫として開いてください。

---
<div align="center">

*このコレクションは学習・実務の出発点です。*<br>
*各リソースで一次情報を確認し、自分の文脈に合わせて活用してください。*

</div>
"""
    write(os.path.join(BASE, "README.md"), body)


# --------------------------------------------------------------------------
# 再生成: index.html（検索・絞り込み付きの単一HTML）
# --------------------------------------------------------------------------
CSS = """
<style>
  :root{
    --bg:#f4f6f6; --surface:#ffffff; --surface-2:#fafbfb;
    --border:#e0e5e5; --text:#191c1c; --muted:#5c6564;
    --accent:#0f7a78; --accent-ink:#0b5250;
    --shadow:0 1px 2px rgba(20,30,30,.05),0 8px 24px -12px rgba(20,40,40,.14);
    --radius:14px;
    --sans:"Hiragino Kaku Gothic ProN","Hiragino Sans","Yu Gothic","YuGothic","Noto Sans JP",Meiryo,system-ui,sans-serif;
    --mono:"SFMono-Regular",ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  }
  @media (prefers-color-scheme:dark){
    :root{
      --bg:#0d1211; --surface:#151b1a; --surface-2:#111716;
      --border:#26302e; --text:#e8eceb; --muted:#95a09e;
      --accent:#31b0ad; --accent-ink:#8fe0dd;
      --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px -14px rgba(0,0,0,.6);
    }
  }
  :root[data-theme="light"]{
    --bg:#f4f6f6; --surface:#ffffff; --surface-2:#fafbfb;
    --border:#e0e5e5; --text:#191c1c; --muted:#5c6564;
    --accent:#0f7a78; --accent-ink:#0b5250;
    --shadow:0 1px 2px rgba(20,30,30,.05),0 8px 24px -12px rgba(20,40,40,.14);
  }
  :root[data-theme="dark"]{
    --bg:#0d1211; --surface:#151b1a; --surface-2:#111716;
    --border:#26302e; --text:#e8eceb; --muted:#95a09e;
    --accent:#31b0ad; --accent-ink:#8fe0dd;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px -14px rgba(0,0,0,.6);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);
       line-height:1.6;-webkit-font-smoothing:antialiased;font-feature-settings:"palt" 1;}
  .wrap{max-width:1180px;margin:0 auto;padding:0 20px 80px;}
  .masthead{padding:44px 0 22px;border-bottom:1px solid var(--border);}
  .kicker{font-size:.75rem;letter-spacing:.18em;text-transform:uppercase;color:var(--accent-ink);
          font-weight:700;margin:0 0 10px;}
  h1.title{font-size:clamp(1.9rem,4.6vw,3rem);line-height:1.1;margin:0 0 12px;font-weight:800;
           letter-spacing:-.01em;text-wrap:balance;}
  .lede{font-size:1.02rem;color:var(--muted);margin:0;max-width:60ch;}
  .stats{display:flex;gap:26px;margin-top:20px;flex-wrap:wrap;}
  .stat{display:flex;align-items:baseline;gap:7px;}
  .stat b{font-size:1.5rem;font-weight:800;font-variant-numeric:tabular-nums;color:var(--text);}
  .stat span{font-size:.82rem;color:var(--muted);}
  .controls{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 88%,transparent);
            backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
            padding:14px 0 12px;border-bottom:1px solid var(--border);margin-bottom:26px;}
  .search-row{display:flex;gap:12px;align-items:center;margin-bottom:12px;}
  .search{flex:1;position:relative;}
  .search input{width:100%;padding:11px 14px 11px 40px;border:1px solid var(--border);
                border-radius:10px;background:var(--surface);color:var(--text);font:inherit;font-size:.95rem;}
  .search input:focus{outline:2px solid var(--accent);outline-offset:1px;border-color:transparent;}
  .search svg{position:absolute;left:13px;top:50%;transform:translateY(-50%);width:17px;height:17px;
              stroke:var(--muted);fill:none;stroke-width:2;}
  .count{font-size:.85rem;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums;}
  .count b{color:var(--text);font-weight:700;}
  .chips{display:flex;gap:8px;flex-wrap:wrap;}
  .chip{--h:180;display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;
        border:1px solid var(--border);background:var(--surface);color:var(--text);font:inherit;
        font-size:.82rem;font-weight:600;cursor:pointer;transition:transform .08s,border-color .15s,background .15s;}
  .chip:hover{transform:translateY(-1px);border-color:hsl(var(--h) 45% 55%);}
  .chip .chip-e{font-size:.95rem;}
  .chip .chip-n{font-size:.7rem;color:var(--muted);font-variant-numeric:tabular-nums;
                background:var(--surface-2);border:1px solid var(--border);border-radius:999px;padding:0 6px;}
  .chip.is-active{background:hsl(var(--h) 60% 94%);border-color:hsl(var(--h) 50% 55%);color:hsl(var(--h) 55% 26%);}
  .chip[data-cat="all"].is-active{background:var(--accent);border-color:var(--accent);color:#fff;}
  .chip[data-cat="all"].is-active .chip-n{background:rgba(255,255,255,.22);border-color:transparent;color:#fff;}
  :root[data-theme="dark"] .chip.is-active{background:hsl(var(--h) 42% 18%);border-color:hsl(var(--h) 50% 45%);color:hsl(var(--h) 70% 78%);}
  :root[data-theme="light"] .chip.is-active{background:hsl(var(--h) 60% 94%);border-color:hsl(var(--h) 50% 55%);color:hsl(var(--h) 55% 26%);}
  @media (prefers-color-scheme:dark){.chip.is-active{background:hsl(var(--h) 42% 18%);border-color:hsl(var(--h) 50% 45%);color:hsl(var(--h) 70% 78%);}}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;}
  .card{--h:180;position:relative;background:var(--surface);border:1px solid var(--border);
        border-radius:var(--radius);padding:18px 18px 16px;box-shadow:var(--shadow);
        border-top:3px solid hsl(var(--h) 60% 50%);display:flex;flex-direction:column;}
  .card.hide{display:none;}
  .card-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px;}
  .num{font-family:var(--mono);font-size:.82rem;font-weight:700;color:hsl(var(--h) 45% 45%);
       font-variant-numeric:tabular-nums;letter-spacing:.02em;}
  :root[data-theme="dark"] .num{color:hsl(var(--h) 55% 68%);}
  :root[data-theme="light"] .num{color:hsl(var(--h) 45% 45%);}
  @media (prefers-color-scheme:dark){.num{color:hsl(var(--h) 55% 68%);}}
  .cat-chip{display:inline-flex;align-items:center;gap:5px;font-size:.72rem;font-weight:600;
            color:var(--muted);padding:3px 8px;border-radius:999px;background:var(--surface-2);
            border:1px solid var(--border);max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
  .cat-e{font-size:.85rem;}
  .card-title{font-size:1.08rem;font-weight:800;margin:0 0 6px;line-height:1.3;letter-spacing:-.005em;}
  .card-overview{font-size:.9rem;color:var(--muted);margin:0 0 12px;flex:1;}
  details.card-more{margin-top:auto;border-top:1px dashed var(--border);padding-top:10px;}
  summary{cursor:pointer;list-style:none;font-size:.85rem;font-weight:700;color:var(--accent-ink);
          display:inline-flex;align-items:center;gap:6px;user-select:none;}
  summary::-webkit-details-marker{display:none;}
  summary::before{content:"›";font-size:1.1rem;line-height:1;transition:transform .18s;display:inline-block;}
  details[open] summary::before{transform:rotate(90deg);}
  .summary-close{display:none;} details[open] .summary-open{display:none;} details[open] .summary-close{display:inline;}
  .detail{padding-top:12px;display:flex;flex-direction:column;gap:14px;}
  .block h4{font-size:.8rem;margin:0 0 6px;font-weight:700;letter-spacing:.01em;}
  .block ul,.block ol{margin:0;padding-left:1.25em;font-size:.85rem;color:var(--text);}
  .block li{margin:3px 0;}
  .block ul{list-style:disc;} .block ol{list-style:decimal;}
  .empty{display:none;text-align:center;padding:60px 20px;color:var(--muted);}
  .empty.show{display:block;}
  footer{margin-top:40px;padding-top:22px;border-top:1px solid var(--border);
         color:var(--muted);font-size:.82rem;text-align:center;line-height:1.7;}
  @media (max-width:560px){.grid{grid-template-columns:1fr;}.search-row{flex-direction:column;align-items:stretch;}.count{align-self:flex-end;}}
  @media (prefers-reduced-motion:reduce){*{transition:none!important;}}
</style>
"""

JS = """
<script>
(function(){
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var chips = Array.prototype.slice.call(document.querySelectorAll('.chip'));
  var input = document.getElementById('q');
  var countEl = document.getElementById('count-n');
  var empty = document.getElementById('empty');
  var activeCat = 'all';
  function apply(){
    var q = (input.value || '').trim().toLowerCase();
    var n = 0;
    cards.forEach(function(c){
      var okCat = activeCat === 'all' || c.getAttribute('data-cat') === activeCat;
      var okQ = !q || c.getAttribute('data-search').indexOf(q) !== -1;
      var show = okCat && okQ;
      c.classList.toggle('hide', !show);
      if(show) n++;
    });
    countEl.textContent = n;
    empty.classList.toggle('show', n === 0);
  }
  chips.forEach(function(chip){
    chip.addEventListener('click', function(){
      activeCat = chip.getAttribute('data-cat');
      chips.forEach(function(c){
        var on = c === chip;
        c.classList.toggle('is-active', on);
        c.setAttribute('aria-pressed', on ? 'true':'false');
      });
      apply();
    });
  });
  input.addEventListener('input', apply);
  apply();
})();
</script>
"""


def build_index_html(cats):
    total = sum(len(c["skills"]) for c in cats)
    res_count = sum(len(s["resources"]) for c in cats for s in c["skills"])
    chips = [f'<button class="chip is-active" data-cat="all" aria-pressed="true">すべて<span class="chip-n">{total}</span></button>']
    for c in cats:
        chips.append(
            f'<button class="chip" data-cat="{c["num"]}" style="--h:{c["hue"]}" aria-pressed="false">'
            f'<span class="chip-e">{c["emoji"]}</span>{esc(c["name"])}<span class="chip-n">{len(c["skills"])}</span></button>'
        )
    chips_html = "\n      ".join(chips)

    cards = []
    for c in cats:
        for s in c["skills"]:
            tools_li = "".join(f"<li>{esc(t)}</li>" for t in s["tools"])
            steps_li = "".join(f"<li>{esc(st)}</li>" for st in s["steps"])
            res_li = "".join(f"<li>{esc(r)}</li>" for r in s["resources"])
            blob = esc(f"{s['title']} {s['overview']} {' '.join(s['tools'])} {c['name']}").lower()
            cards.append(f'''<article class="card" style="--h:{c['hue']}" data-cat="{c['num']}" data-search="{blob}">
        <header class="card-head">
          <span class="num">{esc(s['seq'])}</span>
          <span class="cat-chip"><span class="cat-e">{c['emoji']}</span>{esc(c['name'])}</span>
        </header>
        <h3 class="card-title">{esc(s['title'])}</h3>
        <p class="card-overview">{esc(s['overview'])}</p>
        <details class="card-more">
          <summary><span class="summary-open">詳しく見る</span><span class="summary-close">閉じる</span></summary>
          <div class="detail">
            <div class="block"><h4>🌍 世界最高峰のツール・手法</h4><ul>{tools_li}</ul></div>
            <div class="block"><h4>🛠 実践ステップ</h4><ol>{steps_li}</ol></div>
            <div class="block"><h4>📚 厳選リソース</h4><ul>{res_li}</ul></div>
          </div>
        </details>
      </article>''')
    cards_html = "\n      ".join(cards)

    body = f'''{CSS}
<div class="wrap">
  <header class="masthead">
    <p class="kicker">世界最高のスキル・コレクション ｜ 毎週更新</p>
    <h1 class="title">🏆 使える最高のスキル100</h1>
    <p class="lede">世界中から集めた「一人で問題解決し、AIをレバレッジして稼ぐ」ための実用スキル。{len(cats)}カテゴリ・{total}項目を、ツール・実践ステップ・厳選リソース付きで収録。</p>
    <div class="stats">
      <div class="stat"><b>{len(cats)}</b><span>カテゴリ</span></div>
      <div class="stat"><b>{total}</b><span>スキル</span></div>
      <div class="stat"><b>{res_count}</b><span>厳選リソース</span></div>
    </div>
  </header>
  <div class="controls">
    <div class="search-row">
      <label class="search">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>
        <input id="q" type="search" placeholder="スキル・ツール名で検索（例: SEO, Claude, 確定申告）" aria-label="スキルを検索">
      </label>
      <div class="count"><b id="count-n">{total}</b> 件を表示</div>
    </div>
    <div class="chips">
      {chips_html}
    </div>
  </div>
  <main>
    <div class="grid">
      {cards_html}
    </div>
    <div class="empty" id="empty">該当するスキルが見つかりませんでした。検索語やカテゴリを変えてお試しください。</div>
  </main>
  <footer>
    「1項目 = 1フォルダ」で計{total}フォルダに整理したコレクションのブラウズ版。毎週 月曜 朝9時(JST) に自動更新。<br>
    各リソースで一次情報を確認し、自分の文脈に合わせて活用してください。
  </footer>
</div>
{JS}
'''
    write(os.path.join(BASE, "index.html"), body)


# --------------------------------------------------------------------------
# 再生成: Obsidian Vault
# --------------------------------------------------------------------------
def build_vault(cats):
    def yaml_list(items):
        return "".join(f"\n  - {i}" for i in items)

    def cat_slug(name):
        return name.replace("・", "_").replace("/", "_").replace(" ", "")

    def note_name(n, title):
        return f"{int(n):03d} {safe(title)}"

    def cat_note(num, name):
        return safe(f"{num}_{name}")

    flat = [s for c in cats for s in c["skills"]]
    name_by_n = {s["n"]: note_name(s["n"], s["title"]) for s in flat}

    # スキルノート
    for c in cats:
        for s in c["skills"]:
            n = s["n"]
            prev_link = f"[[{name_by_n[n-1]}]]" if n - 1 in name_by_n else "—"
            next_link = f"[[{name_by_n[n+1]}]]" if n + 1 in name_by_n else "—"
            tools_md = "\n".join(f"- {t}" for t in s["tools"])
            steps_md = "\n".join(f"{i+1}. {st}" for i, st in enumerate(s["steps"]))
            res_md = "\n".join(f"- {r}" for r in s["resources"])
            catnote = cat_note(c["num"], c["name"])
            cslug = cat_slug(c["name"])
            fm = (
                "---\n"
                f"番号: {n}\n"
                f'カテゴリ: "[[{catnote}]]"\n'
                "状態: 未着手\n"
                f'タグ:{yaml_list(["スキル100", "スキル100/" + cslug])}\n'
                f"ツール:{yaml_list(s['tools'])}\n"
                f"aliases:{yaml_list([s['title']])}\n"
                "---\n"
            )
            body = f"""{fm}
# {c['emoji']} {s['title']}

> [!abstract] 概要
> {s['overview']}

**カテゴリ**: [[{catnote}]]　｜　**No.** {n} / {len(flat)}

## 🌍 世界最高峰のツール・手法
{tools_md}

## 🛠 実践ステップ
{steps_md}

## 📚 厳選リソース
{res_md}

## 📝 学習メモ
-

---
◀ {prev_link}　｜　[[{catnote}]]　｜　[[{HOME}]]　｜　{next_link} ▶
"""
            write(os.path.join(VAULT, "スキル", f"{note_name(n, s['title'])}.md"), body)

    # カテゴリMOC
    for c in cats:
        cs = c["skills"]
        links = "\n".join(f"- [[{note_name(s['n'], s['title'])}]] — {s['overview']}" for s in cs)
        body = f"""---
タグ:
  - スキル100/MOC
カテゴリ番号: {int(c['num'])}
---

# {c['emoji']} {c['name']}

> {c['tagline']}

**収録スキル**: No.{cs[0]['seq']}〜{cs[-1]['seq']}（{len(cs)}個）　｜　[[{HOME}|🏠 ホームへ]]

## 📚 スキル一覧
{links}

## ✅ 進捗（Dataview）
> [!info] 下の表は **Dataviewプラグイン** で自動表示されます（未導入なら上のリストを参照）。

```dataview
TABLE 状態, ツール
FROM #スキル100/{cat_slug(c['name'])}
SORT 番号 ASC
```
"""
        write(os.path.join(VAULT, "カテゴリ", f"{cat_note(c['num'], c['name'])}.md"), body)

    # ホーム
    cat_links = "\n".join(
        f"- {c['emoji']} [[{cat_note(c['num'], c['name'])}]] — {c['tagline']}"
        f"（No.{c['skills'][0]['seq']}〜{c['skills'][-1]['seq']}）"
        for c in cats
    )
    home = f"""---
タグ:
  - スキル100/ホーム
---

# 🏆 使える最高のスキル100

世界中から集めた「一人で問題解決し、AIをレバレッジして稼ぐ」ための実用スキル集。
**{len(cats)}カテゴリ・{len(flat)}ノート**。各ノートに世界最高峰のツール・実践ステップ・厳選リソースを収録。

> [!tip] 使い方
> 各スキルノートのプロパティ **状態** を `未着手 → 学習中 → 習得済` に更新すると、下のダッシュボードに進捗が反映されます（[[_使い方]] 参照）。

## 🗂 カテゴリ
{cat_links}

## 📊 進捗ダッシュボード（Dataview）
> [!info] **Dataviewプラグイン**が必要です。設定 → コミュニティプラグイン → 「Dataview」を導入・有効化してください。

### 状態別のスキル数
```dataview
TABLE length(rows) AS 件数
FROM #スキル100
WHERE 番号
GROUP BY 状態
```

### 全スキル一覧
```dataview
TABLE 状態, カテゴリ, ツール
FROM #スキル100
WHERE 番号
SORT 番号 ASC
```

### 習得済みスキル
```dataview
LIST
FROM #スキル100
WHERE 状態 = "習得済"
SORT 番号 ASC
```

---
*このコレクションは学習・実務の出発点です。各リソースで一次情報を確認し、自分の文脈に合わせて活用してください。*
"""
    write(os.path.join(VAULT, f"{HOME}.md"), home)

    # 使い方
    usage = f"""# 📖 使い方（Obsidian連携）

この `obsidian-vault` フォルダは、そのまま **Obsidianの保管庫（Vault）** として開けます。

## 🚀 導入手順
1. Obsidianを起動 → **「保管庫を開く」→「フォルダを保管庫として開く」**
2. この `obsidian-vault` フォルダを選択
3. [[{HOME}]] を開く（ホーム／ダッシュボード）

## 🔌 おすすめプラグイン
- **Dataview** … [[{HOME}]] とカテゴリノートの進捗ダッシュボードを表示（実質必須）
- **Tasks / Templater** … 学習メモやタスク管理を強化（任意）

## 🏷 データ構造
- **プロパティ**: `番号` / `カテゴリ`（リンク）/ `状態` / `ツール` / `aliases`
- **タグ**: `#スキル100`（全体）, `#スキル100/<カテゴリ>`（分野別）, `#スキル100/MOC`（カテゴリ索引）
- **リンク**: 各スキルは「前後のスキル・カテゴリMOC・ホーム」に相互リンク

## ✅ 進捗の付け方
各スキルノート上部のプロパティ **状態** を編集：
`未着手` → `学習中` → `習得済`
→ [[{HOME}]] のダッシュボードに自動集計されます。

## 🔄 このVaultは毎週更新されます
元の 100-skills コレクションは毎週（月曜 朝9時 JST）自動で最新化され、
その内容が `build.py` でこのVaultにも反映されます。
"""
    write(os.path.join(VAULT, "_使い方.md"), usage)

    # .obsidian（既にあれば上書きしない）
    od = os.path.join(VAULT, ".obsidian")
    if not os.path.exists(os.path.join(od, "app.json")):
        write(os.path.join(od, "app.json"),
              '{\n  "newFileLocation": "folder",\n  "newFileFolderPath": "スキル",\n  "showFrontmatter": true,\n  "readableLineLength": true\n}\n')


# --------------------------------------------------------------------------
def main():
    cats = collect()
    total = sum(len(c["skills"]) for c in cats)
    if "--check" in sys.argv:
        for c in cats:
            print(f"{c['num']}_{c['name']}: {len(c['skills'])}")
        print(f"TOTAL: {total} skills in {len(cats)} categories")
        return
    build_category_readmes(cats)
    build_top_readme(cats)
    build_index_html(cats)
    build_vault(cats)
    print(f"✓ rebuilt from {total} skills in {len(cats)} categories")
    print("  - top README, category READMEs, index.html, obsidian-vault/")


if __name__ == "__main__":
    main()
