# WebCanon

**AI のための、ポリシー準拠 Web 取得レイヤー。**

*Read this in [English](README.md).*

WebCanon は、与えられた **URL** を、信頼でき・ポリシー検証済みで・出典付きの
LLM 向けコンテキストへ変換する OSS の取得レイヤーです。

`robots.txt`（RFC 9309）を評価し、（任意で独自 AI を用いて）`llms.txt` による
LLM 向け代替 URL へ解決し、SSRF ガードの背後でコンテンツを取得し、HTML を構造化
Markdown へ変換し、取得した全ドキュメントに対して**完全な出典証跡（provenance）**
を返します。

> **スコープ:** WebCanon は *与えられた URL を正しく・ポリシー準拠でスクレイピング
> する* ことに焦点を当てます。**WEB 検索エンジンはスコープ外**です（候補 URL を
> 見つけるのは別の関心事）。スクレイピング処理と AI 処理は差し替え可能です。

## なぜ必要か

多くの AI パイプラインは関心事が混在しています。検索スニペットをそのままモデルへ
渡し、URL を無検証でクローンし、`robots.txt` を見ず、`sitemap.xml` を無視し、出典
証跡を失います。WebCanon はこれらを 1 つの品質契約に分離します。

| 概念 | 役割 |
| --- | --- |
| Search | 候補 URL を見つける |
| Fetch | URL の内容を取得する |
| Respect | 取得前に `robots.txt` ポリシーを評価する |
| Resolve | `llms.txt` / canonical により LLM 向け URL へ読み替える |
| Extract | HTML/PDF を LLM 向け Markdown へ変換する |
| Ground | 出典・取得経路・変換根拠を保持する |

### 取得の憲法（The retrieval constitution）

1. 検索結果は手がかりであって、情報源ではない。
2. `robots.txt` は取得の**前に**評価する。
3. `llms.txt` は取得を*ガイド*できるが、ポリシーを上書きできない。
4. 変換した全ドキュメントは出典証跡を保持しなければならない。
5. Web コンテンツは**信頼できない（untrusted）入力**である。
6. Markdown はインターフェースであり、真実の源ではない。
7. 抽出品質は測定可能でなければならない。

## インストール

```bash
pip install webcanon
```

JavaScript レンダリングが必要なページ向け（ヘッドレスブラウザ・任意）:

```bash
pip install "webcanon[headless]"
python -m playwright install chromium
```

AI による `llms.txt` 解決向け（Anthropic / OpenAI / Gemini・任意）:

```bash
pip install "webcanon[ai]"       # anthropic (Claude)。または [openai] / [gemini]
```

有効化の方法は下記 [AI プロバイダと API キー](#ai-プロバイダと-api-キー) を参照してください。

ソースから:

```bash
pip install -e ".[dev]"
```

## クイックスタート

```python
from webcanon import WebCanon

client = WebCanon()
result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)

print(result.document.markdown)        # 抽出された Markdown
print(result.policy.robots.verdict)    # 例: "allowed_implicit"
print(result.provenance.source_hash)   # ソース本文の sha256
```

`result` は `RetrievalResult`（**Retrieval Bill of Materials**）です。
`result.to_dict()` で JSON シリアライズ可能な監査レコードを取得できます
（なぜその URL を選んだか、robots が許可したか、`llms.txt` による読み替えが
発生したか、抽出品質、再現用ハッシュ）。

デフォルトの `User-Agent` プロダクトトークンは **`WebCanon`** です。

## カスタマイズフック

スクレイピングのトランスポート、HTML→Markdown 変換器、`llms.txt` を推論する AI は
すべて**差し替え可能な callable** です。`RetrievalConfig` に渡します。

```python
from webcanon import WebCanon, AiHint
from webcanon.config import RetrievalConfig

def my_ai(ctx):
    # ctx には要求 URL・パース済み llms.txt・robots 判定が入る。
    # URL の読み替えや特別なリクエストヘッダーを決定する。
    return AiHint(url=ctx.requested_url + ".md", headers={"Accept": "text/markdown"},
                  reason="prefer markdown variant")

client = WebCanon(RetrievalConfig(
    ai_resolver=my_ai,        # llms.txt + URL に対する AI 推論
    # fetcher=my_fetcher,     # 独自のスクレイピングトランスポート
    # extractor=my_extractor, # 独自の HTML -> Markdown
))
result = client.retrieve_url("https://example.com/docs/api", ai_reasoning=True)
```

robots.txt が常に優先されます。`AiHint` が Disallow の URL を指した場合、その
ヒントは（URL もヘッダーも）破棄され、通常の解決が継続されます。
詳細は [`docs/customization.md`](docs/customization.md)（[日本語版サイト](https://bon2016.github.io/webcanon/)）を参照してください。

## AI プロバイダと API キー

WebCanon は3つのプロバイダ向けの組み込み AI リゾルバを同梱しています。環境変数で
1つを有効化します（CLI の `--ai` とライブラリの `ai_resolver_from_env()` で共通）:

| プロバイダ | `WEBCANON_AI_PROVIDER` | **API キーの環境変数** | インストール extra | 既定モデル | キー取得 |
| --- | --- | --- | --- | --- | --- |
| Anthropic (Claude) | `anthropic` | `ANTHROPIC_API_KEY` | `pip install "webcanon[ai]"` | `claude-opus-4-8` | <https://console.anthropic.com/> |
| OpenAI | `openai` | `OPENAI_API_KEY` | `pip install "webcanon[openai]"` | `gpt-5` | <https://platform.openai.com/api-keys> |
| Google Gemini | `gemini` | `GEMINI_API_KEY`（または `GOOGLE_API_KEY`） | `pip install "webcanon[gemini]"` | `gemini-2.5-pro` | <https://aistudio.google.com/apikey> |

プロバイダとモデルは **環境変数** でも **コマンドライン引数** でも指定できます
（引数が優先）:

| | 環境変数 | コマンドライン引数 |
| --- | --- | --- |
| プロバイダ | `WEBCANON_AI_PROVIDER` | `--ai-provider {anthropic,openai,gemini}` |
| モデル | `WEBCANON_AI_MODEL` | `--ai-model MODEL` |

- `--ai-provider` は `--ai` を含意します（両方指定する必要はありません）。
- 未設定 / `none` で無効（組み込みルールエンジンにフォールバック）。
- API キーは常に上表の環境変数から読み込まれます。

### 代表的なモデル

各プロバイダが提供するモデルはそのまま指定できます（WebCanon はモデル ID を
そのまま渡します）。**太字**が既定。全一覧と指針は
[`docs/ai-models.md`](docs/ai-models.md) を参照してください。

| プロバイダ | 代表的なモデル ID |
| --- | --- |
| Anthropic | **`claude-opus-4-8`**, `claude-fable-5`, `claude-sonnet-4-6`, `claude-haiku-4-5` |
| OpenAI | **`gpt-5`**, `gpt-5-mini`, `gpt-4o`, `gpt-4o-mini` |
| Gemini | **`gemini-2.5-pro`**, `gemini-2.5-flash`, `gemini-2.5-flash-lite` |

本ユースケース（`llms.txt` の小さな判断）では高速・低コストなモデルで十分な
ことが多いです（例: `gpt-4o-mini` / `gemini-2.5-flash` / `claude-haiku-4-5`）。
不正・廃止済みの ID を指定した場合はルールエンジンにフォールバックするため、
モデル文字列が原因で取得が失敗することはありません。

```bash
# コマンドライン引数（プロバイダ・モデルを引数で指定）
export OPENAI_API_KEY=sk-...
webcanon fetch https://example.com/docs/api --ai-provider openai --ai-model gpt-4o

# 環境変数
export WEBCANON_AI_PROVIDER=openai
export OPENAI_API_KEY=sk-...
# 任意: export WEBCANON_AI_MODEL=gpt-4o
webcanon fetch https://example.com/docs/api --ai

# Google Gemini
export WEBCANON_AI_PROVIDER=gemini
export GEMINI_API_KEY=...           # GOOGLE_API_KEY でも可
webcanon fetch https://example.com/docs/api --ai

# Anthropic (Claude)
export WEBCANON_AI_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
webcanon fetch https://example.com/docs/api --ai
```

注意:

- AI は取得を*ガイド*するだけです。選んだ URL は `robots.txt` と SSRF ガードで
  再検証され、安全なヘッダー（`Accept` など）のみ送信されます。
- プロバイダの SDK 未インストールや API エラー時は、リゾルバは何もせずルール
  エンジンにフォールバックします（AI が原因で取得が失敗することはありません）。
- OpenAI 互換エンドポイント: コードで `OpenAiAiResolver(base_url=...)` を渡す
  （または `OPENAI_BASE_URL` を設定）。

## CLI

```bash
webcanon fetch https://example.com/docs/api --ai --llms prefer --robots respect
webcanon fetch https://example.com/docs/api --json --report report.json
webcanon inspect https://example.com/docs/api
```

## ステータス

これは **v0.1** — URL 取得の品質ベースラインです。

- URL 正規化・origin 抽出
- `robots.txt` 取得 + RFC 9309 評価エンジン
- `llms.txt` パース + LLM 向け URL 解決（任意で独自 AI）
- `sitemap.xml` パース（URL 発見）
- SSRF ガード付き HTTP 取得（リダイレクト各ホップで再検査）
- HTML → Markdown 抽出（標準ライブラリのみ）+ hidden text 警告
- 出典証跡付き JSON 出力
- CLI（`fetch`, `inspect`）

アーキテクチャ・ポリシーモデル・robots 準拠・`llms.txt` 解決・抽出品質・
セキュリティモデル・ロードマップは [`docs/`](docs/) を参照してください。
ドキュメントサイト: <https://bon2016.github.io/webcanon/>

## ライセンス

Apache-2.0。[LICENSE](LICENSE) を参照してください。
