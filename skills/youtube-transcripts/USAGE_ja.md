# ローカル実行ガイド（日本語）

YouTube チャンネルの全動画をテキスト化して、1つのコンテキストファイルにまとめる手順です。

> **重要**: この処理には YouTube への通常のインターネット接続が必要です。
> Claude Code の web セッションなど一部のサンドボックス環境は YouTube を
> ブロックしており（`403 Forbidden`）、その場合は動画を取得できません。
> **あなたのローカル PC で実行してください。**

---

## 事前確認：Python が入っているか

ターミナル（Mac）／PowerShell（Windows）で確認します。

```bash
python3 --version    # Mac / Linux
python --version     # Windows
```

`Python 3.9` 以上が表示されれば OK です。表示されない・古い場合は、下の各 OS 手順でインストールします。

---

## 🍎 Mac の場合

### 1. Homebrew を入れる（未導入なら）

Mac 用のパッケージ管理ツールです。Python や ffmpeg の導入に使えます。

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

インストール後、画面の指示に従って `PATH` を通します（Apple Silicon の場合、案内される
`eval "$(/opt/homebrew/bin/brew shellenv)"` を実行）。

### 2. Python と ffmpeg を入れる

```bash
brew install python ffmpeg
```

（ffmpeg は後述の Whisper 音声認識を使う場合に必要。字幕だけなら無くても動きます）

### 3. yt-dlp を入れる

```bash
python3 -m pip install -U yt-dlp
```

### 4. リポジトリを取得してスクリプトを実行

```bash
git clone https://github.com/dakara0901-alt/skills.git
cd skills/skills/youtube-transcripts
python3 scripts/youtube_transcripts.py "https://www.youtube.com/@AI仙人ch/videos"
```

---

## 🪟 Windows の場合

### 1. Python を入れる

[python.org](https://www.python.org/downloads/) からインストーラを入れます。
**インストール時に「Add python.exe to PATH」に必ずチェック** を入れてください。

### 2. yt-dlp を入れる

PowerShell を開いて：

```powershell
python -m pip install -U yt-dlp
```

### 3. （任意）ffmpeg を入れる

Whisper を使う場合のみ必要です。`winget install Gyan.FFmpeg` または
[ffmpeg.org](https://ffmpeg.org/download.html) から。字幕だけなら不要です。

### 4. リポジトリを取得して実行

```powershell
git clone https://github.com/dakara0901-alt/skills.git
cd skills\skills\youtube-transcripts
python scripts\youtube_transcripts.py "https://www.youtube.com/@AI仙人ch/videos"
```

（git が無い場合は、GitHub の緑の「Code」ボタン → Download ZIP でも取得できます）

---

## 実行後にできるもの

`transcripts/` フォルダに以下が生成されます。

| ファイル | 中身 |
| --- | --- |
| `001_<動画タイトル>.txt` など | 動画 1 本ごとの文字起こし（先頭にタイトルと URL） |
| `context.md` | **全動画を 1 つに結合したコンテキスト**（要約や AI への投入用） |
| `index.json` | 各動画の取得元記録（`captions`＝字幕／`whisper`＝音声認識／`null`＝取得不可） |

---

## よく使うオプション

```bash
# まず5本だけで試す（動作確認におすすめ）
python3 scripts/youtube_transcripts.py "https://www.youtube.com/@AI仙人ch/videos" --limit 5

# 字幕が無い動画も音声認識で拾う（先に: pip install -U openai-whisper）
python3 scripts/youtube_transcripts.py "https://www.youtube.com/@AI仙人ch/videos" --whisper

# 英語字幕を優先
python3 scripts/youtube_transcripts.py "..." --langs en,ja

# 出力先フォルダを変える
python3 scripts/youtube_transcripts.py "..." --out ./ai_sennin
```

一度取得した動画のテキストは次回スキップされるので、途中で止めても再実行すれば
続きから進みます（取り直したい場合は `--overwrite`）。

すべてのオプションは `SKILL.md` の表を参照してください。

---

## つまずきやすい点

- **`python3` が見つからない** → Windows は `python`、Mac で未導入なら手順 2 を実施。
- **`yt-dlp: command not found`** → `python3 -m pip install -U yt-dlp` を再実行。
  呼び出しは `python3 scripts/youtube_transcripts.py ...` の形なのでパスは問題になりにくいです。
- **`403` や `Sign in to confirm you're not a bot`** → 一時的に YouTube 側で弾かれることが
  あります。`yt-dlp -U` で最新化、少し時間を置く、または `--limit` で件数を絞ると通りやすいです。
- **Whisper が遅い** → `--whisper-model tiny` で軽くできます（精度は下がる）。字幕がある動画は
  Whisper 不要なので、まずは `--whisper` なしで実行してください。

---

## 権利・利用について

文字起こしは第三者の動画から生成されるものです。個人的な学習・分析の範囲で利用し、
制作者の権利および YouTube の利用規約を尊重してください。
