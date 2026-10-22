# Agent Skills

AIエージェントに任せる日々の作業を、再利用できるSkillとしてまとめる個人用リポジトリです。特定の分野に限定せず、実際に必要になったものから追加します。

リポジトリ名は当面 `agent-control-plane` のままです。大きな制御フレームワークや独自の認証基盤は作りません。

## 現在のSkill

| Skill | できること |
| --- | --- |
| [controlled-github](skills/controlled-github/SKILL.md) | Gitの状態確認、対象ファイルを限定したcommit、送信する全commitを確認したpush、push済みbranchからのPR作成 |
| [spec-driven-development](skills/spec-driven-development/SKILL.md) | 要求を仕様・受入基準・小さなタスクに整理し、依頼された範囲でテスト・実装・検証・引き継ぎを進める |
| [secret-checks](skills/secret-checks/SKILL.md) | ローカル環境と既存hookを診断し、秘密情報の検査hookを導入・検証・更新・切り戻し・解除・cleanupする |

## 導入と使い方

使いたいSkillを `skills/` からフォルダごと、利用するエージェントが認識するSkillディレクトリへ配置してください。配置場所や呼び出し方法は利用製品の設定に従います。同名のSkillがある場合は、差分を確認してから更新してください。この作業で自動インストールは行いません。

各Skillは単独で利用でき、このリポジトリの他のファイルに依存しません。`controlled-github`にはGitとPython 3.10以上、PR操作には設定済みのGitHub CLIが必要です。`spec-driven-development`自体に追加ツールは不要で、開発先の既存ツールを使います。

`secret-checks`はLinux／WSL2、Git（`/usr/bin/git`）、Python 3.10以上、POSIX shellを対象とします。秘密情報のPython検査自体は標準ライブラリで動きますが、導入・更新には[固定版の画像検証環境](skills/secret-checks/references/images-and-publication.md)も必要です。Gitleaks版または両方を使うcombined版を選ぶ場合は、[固定版ランナーの準備](skills/secret-checks/references/runner.md)が必要です。

### GitHubから導入する（Codex）

このリポジトリを手元にcloneせず、GitHubから取得して導入することもできます。Codexの`skill-installer`は他のGitHubリポジトリからの導入に対応しています。リポジトリ単位で使う場合の配置先は、導入先のルートにある`.agents/skills/`です。[OpenAI公式ドキュメント](https://learn.chatgpt.com/docs/build-skills)

導入先リポジトリでCodexを開き、次の依頼を送ってください。配布元は[main branchのskillsディレクトリ](https://github.com/DharmaDoll/agent-control-plane/tree/main/skills)です。

```text
$skill-installer

以下のGitHubリポジトリから、3つのSkillを導入してください。

repository: DharmaDoll/agent-control-plane
ref: main
paths:
- skills/spec-driven-development
- skills/controlled-github
- skills/secret-checks

配置先は、このリポジトリのルートにある .agents/skills/ としてください。
各SkillはSKILL.mdだけでなく、参照資料やscriptを含むフォルダ全体を取得してください。

- installerの --repo・--ref・--path を別々に指定する
- --dest には導入先リポジトリの .agents/skills/ の絶対パスを指定する
- --method download を使い、失敗時は別方式へ切り替えず停止する
- 同名Skillが既にある場合は上書きせず報告する
- 認証設定や既存のAGENTS.mdは変更しない
- commit・pushはしない
- 導入後に各SkillのSKILL.mdと参照ファイルの存在を確認する
```

一部だけ必要なら、`paths`から不要なSkillを外してください。リポジトリのルートにある`AGENTS.md`や`skills_plan/`を導入先へコピーする必要はありません。

- **branchは明示する**：URLの解釈に任せず、repository・ref・pathを分けて指定します。`/`を含むbranch名を使う場合も同様です。
- **配置先は明示する**：installerのデフォルト配置先に任せず、対象リポジトリへ導入します。個人の全リポジトリで共通利用したい場合は、配置先を`~/.agents/skills/`へ変更できます。同名Skillの重複配置は避けてください。
- **取得した版は自動更新されない**：更新時は差分を確認して置き換えます。同じ版を再現したい場合は、`ref`にbranch名ではなくcommit SHAを指定します。

導入後はCodexの`/skills`で認識を確認してください。表示されない場合はCodexを再起動します。Skillの取得・配置と、GitHub操作に必要な認証設定は別の作業です。[OpenAI公式ドキュメント](https://learn.chatgpt.com/docs/build-skills)

### 利用例

依頼例：

> controlled-githubを使って、このworktreeのbranchと差分、commit・pushの前提を確認して。まだstage・commit・push・設定変更はしないで。

> controlled-githubを使って、合意した変更だけをcommitし、確認済みのremote・branchへpushして。認証設定は変えず、PRは作成しないで。

対象や権限が不明なら、書き込み前に確認します。「確認だけ」「commit」「push」「PR作成」は別の操作です。

開発の進め方を整える場合：

> spec-driven-developmentを使って、この機能の仕様・受入基準・実装計画・テスト計画を整理して。今回は提案までで、ファイルは変更しないで。

> spec-driven-developmentを使って、合意した計画をタスクごとに実装・検証して。結果と次の作業を既存の作業記録に残して。commit・pushはしないで。

小さな変更には短い確認だけを使い、複数工程の作業には[作業記録テンプレート](skills/spec-driven-development/assets/work-item.md)を必要に応じて使います。開発とGitHub操作のSkillは互いに独立しており、一方の利用がもう一方の操作許可になることはありません。

秘密情報の検査を導入する場合：

> secret-checksを使って、このリポジトリの環境と既存hookを確認し、適した方法で導入して。設定と拒否動作を検証し、戻し方も報告して。

> secret-checksを使って、使わなくなった検査hookを解除し、管理対象の不要なbundleをcleanupして。

Skillのコピーだけではhookは有効になりません。導入時に環境を診断し、既存hookや共有worktreeがある場合は統合方法を検討します。通常のcommit・pushでは、Git標準hookが検査を呼び出します。導入・更新・切り戻し・解除・cleanupの具体的な操作は[導入手順](skills/secret-checks/references/installation.md)、検査範囲と適用できない条件は[制限事項](skills/secret-checks/references/limitations.md)にあります。

### Gitleaksはどこに配置・実行されるか

新規のGitleaks／combined方式では**Dockerを優先**します。上記の`skill-installer`による取得だけではランナーやDockerは入りません。hook導入時に、固定版Gitleaksの検出処理を組み込んだ専用ランナーを検証し、それと固定設定だけを含む最小イメージをローカルで作ります。Dockerが使えない場合は停止し、ネイティブ方式へ黙って切り替えません。

| 段階 | 配置先・動作 |
| --- | --- |
| Skillの取得 | `<repo>/.agents/skills/secret-checks/`に手順・script等を配置。hookは未有効 |
| バイナリの準備 | 明示した取得・一時配置先に用意。管理scriptはダウンロードしない |
| hookの導入 | 通常は`<repo>/.git/secret-checks/bundles/<bundle-id>/`にhook・検証済みバイナリ・image IDを保存 |
| イメージの配置 | ローカルDocker daemonがストレージを管理。コンテナ内の実行ファイルは`/gitleaks-runner` |
| Gitleaksを実行するhook | ホスト側で検査対象を取得し、入力の区切りを保ってstdinで渡す。1 hookにつき1コンテナで検査し、終了後に削除。新規combined導入ではpush時のみ |

コンテナにはリポジトリやDockerソケットをマウントせず、ネットワークなし・非root・read-onlyで実行します。検査内容を一時ファイルやイメージへ保存しません。ホスト側の`bin/gitleaks-runner`は再構築用に保持しますが、Docker方式では直接実行しません。Docker daemonとPython・Gitはホスト側に必要です。daemonのインストール、権限・PATHの変更は自動では行いません。

ランナーはGo 1.26.8と固定した依存関係で事前にビルドし、SHA-256を照合します。Goが必要なのはビルド環境だけです。準備済み成果物を`--gitleaks-runner /path/to/verified/gitleaks-runner`で渡してください。公式Gitleaks CLIの`--gitleaks`とは別物です。[オフラインビルド手順](skills/secret-checks/references/runner.md)を参照してください。hook実行時にダウンロードやビルドはしません。

両方の検査を導入する依頼例：

> secret-checksを使って、このリポジトリにcombined方式を`--runtime docker`で導入して。固定版ランナーの取得元・準備場所・bundle配置先・image IDを報告して。既存の検証済みランナーが使えるか確認し、なければ承認済みの取得・ビルド手順を使って。Dockerや取得手順が使えない場合は停止し、ネイティブ方式へ切り替えないで。導入後は設定・整合性・拒否動作を検証し、解除・cleanupで何が残るかも報告して。commit・pushはしないで。

既存の導入先は自動移行しません。旧版から初めて更新する際は`update --gitleaks-runner ...`を指定します。Dockerへ変更する場合は`--runtime docker`、Python単独方式から併用へ変更する場合は`--engine combined`も追加します。旧bundleへのrollbackは可能です。ネイティブ方式は明示的に選んだ場合のみ利用します。

`uninstall`はhookを解除し、続く`cleanup --apply`は管理対象の不要なbundleを削除します。共有され得るDockerイメージは保持してIDを報告し、元の取得ファイルやSkill本体も削除しません。イメージ削除は利用先を確認したうえで別途行います。[Docker方式の手順と制約](skills/secret-checks/references/docker.md)、[配置・取得・検証・削除の管理方針](skills/secret-checks/references/gitleaks.md)を参照してください。

Python方式でGitがhookを起動し、indexとcommitメッセージの検査結果を受けて処理を続行・中止する流れは、[Python hookの実行フロー](skills/secret-checks/references/python-hook-flow.md)にまとめています。実装に基づく英語の技術文書で、ユーザー名・導入先のプロジェクト名・実際のbundle IDを含まない例を使っています。

Gitleaks方式の詳しい実行経路は、[Gitleaks hookとGoランナーの実行フロー](skills/secret-checks/references/gitleaks-hook-flow.md)にまとめています。GoへGitleaksをライブラリとして組み込む仕組み、入力ごとの分離、fragment処理、完了結果の照合、Dockerの実行・終了処理を説明しています。

新規導入はcombined／Dockerがデフォルトです。`pre-commit`と`commit-msg`はPythonのみ、`pre-push`はPython → Gitleaksの両方を実行します。画像検証・大量投入制限は維持し、必須の検査で検出・検査不能・スキャナ欠落があれば拒否します。commit時にもGitleaksを使う場合は、導入・更新時に`--commit-gitleaks on`を指定してください。

既存環境の通常更新では現在の方式とcommit時の設定を保持します。旧combined環境を新方針へ切り替えるには、明示的に`--commit-gitleaks off`を指定します。Pythonが見逃した秘密情報はローカル履歴に入り得るため、公開前のpush検査とは保証が異なります。[combined方式の導入と制約](skills/secret-checks/references/combined.md)を確認してください。Skillをコピーしても既存hookは自動更新されません。

## 静止画像の許可と大量公開の停止

PNG・JPEG・WebP・BMP・GIF・TIFF・HEICの静止画像と、制限したSVGを扱います。形式と拡張子の一致、デコード、画素数、フレーム／ページ数を検証し、画像は1件5 MiB・2,000万画素まで許可します。アニメーション・複数ページ・破損・未対応入力は拒否します。SVGは描画せず、外部参照・スクリプト・埋め込み画像等を拒否し、テキストの秘密情報検査も続けます。

ラスター画像の内容・メタデータには秘密情報検査やOCRを行いません。結果には許可画像の件数と「内容は未検査」を表示します。画像の検証は固定版Pillow・pillow-heif・defusedxmlを入れた専用Python環境から、メモリ・CPU・時間を制限したホスト側子プロセスで実行します。Gitleaksは引き続きDockerを優先します。依存関係は自動インストールせず、既存hookも自動更新しません。

大量投入は、commitあたり追加・変更100ファイル／20 MiB、pushあたり新たに公開する500種類のblob／50 MiBを上限として停止します。commitはindexのファイル全体、pushは途中で削除された版を含む履歴を対象にします。既存のテキスト検査上限も維持します。新規branchのpushは到達可能な履歴全体を保守的に計上するため、大きな既存リポジトリでは停止する場合があります。

これは大量投入による事故を抑える制御であり、少量の個人情報、画像内の機密情報、分割した流出やWeb/API経由の変更まで防ぐものではありません。[許可形式・依存環境・集計規則・制限事項](skills/secret-checks/references/images-and-publication.md)を確認してください。

## 認証と安全上の前提

認証の初期設定は人間が行います。[初期設定手順](skills/controlled-github/references/setup.md)には、HTTPSで既存の`gh`認証をGit credential helper経由で使う方法を含めています。実行時にtokenを取得・表示したり、失敗を理由に認証方式を切り替えたりはしません。

付属の[宛先検査helper](skills/controlled-github/references/target-check.md)は読み取り専用です。期待するworktree・host・repository・transportをローカル設定と照合し、複数push先などを検出すると停止します。PASSは認証成功やpush権限を保証するものではありません。

Skill自体はsandboxではありません。権限の強制は実行環境やGitHub側の保護規則に依存します。信頼できないGit設定・hook・実行環境を安全にする仕組みではありません。

## 検証

`controlled-github`の自動テストはリポジトリのルートで実行します。使い捨てのローカルGitリポジトリだけを使い、GitHubには接続しません。

```sh
python3 -B -m unittest discover -s skills/controlled-github/evals -p 'test_*.py' -v
```

[検証記録](skills/controlled-github/evals/validation.md)では、自動テストと未実施のAgent動作評価・live GitHub検証を区別しています。Skillをコピーした後は、そのフォルダ内で `python3 -B -m unittest discover -s evals -p 'test_*.py' -v` を実行できます。

`spec-driven-development`はMarkdownによる手順です。[動作評価シナリオ](skills/spec-driven-development/evals/scenarios.md)で、軽量な変更、計画のみの依頼、テストの失敗、セッション再開などを評価します。文書の形式・参照チェックと、Agentが実際に手順を守るかの評価は区別します。

`secret-checks`のPython版と導入管理のテストは、使い捨てのローカルGitリポジトリで実行します。以下の`python3`には、[固定版の画像デコーダーを準備した環境](skills/secret-checks/references/images-and-publication.md)のPythonを使ってください。画像対応と導入管理の検証にはその依存関係が必要です。

```sh
python3 -B -m unittest discover -s skills/secret-checks/evals -p 'test_scan_sensitive.py' -v
python3 -B -m unittest discover -s skills/secret-checks/evals -p 'test_manage_hooks.py' -v
```

ランナーの実物と公式Gitleaks CLIの比較テストは、照合済みの両方のbinaryを指定して実行します。Docker実機テストを含める場合は`SECRET_CHECKS_DOCKER=1`も指定します。

```sh
SECRET_CHECKS_RUNNER=/path/to/verified/gitleaks-runner SECRET_CHECKS_GITLEAKS=/path/to/verified/gitleaks python3 -B -m unittest discover -s skills/secret-checks/evals -p 'test_*.py' -v
```

binary未指定時はGitleaksの実物を必要とするケースがskipになります。[検証記録](skills/secret-checks/evals/validation.md)では、実行結果と未実施のAgent動作評価・live環境検証を区別します。このリポジトリにはスキャナー・hook・テストの正本を置き、`product-security-guidance`には設計意図と実装への参照を残します。

Dockerの実物を使うテストは、上記に加えて環境変数`SECRET_CHECKS_DOCKER=1`を指定します。ローカルdaemonに検証用イメージと一時コンテナを作成するため、明示的な指定がない場合はskipします。コンテナは検査後に削除し、イメージは保持します。

## 管理方針

READMEは日本語、Skillの指示・技術文書・コードは英語で管理します。英語が常に優れると断定するものではなく、指示の重複と翻訳のずれを避けるための運用方針です。

- 一つのSkillは一つの用途に絞り、単独で持ち出せるようにする。
- 手順はMarkdown、判断がぶれやすい検査は小さなscriptにする。
- 実際に必要になるまで共通frameworkや設定ファイルを増やさない。
- 実行した検証と、未検証の期待動作を分けて記録する。

共通ルールは[AGENTS.md](AGENTS.md)と[開発原則](docs/principles.md)にあります。旧GitHub文書のリンクは移行案内として残しています。`skills_plan/` は検討用の原案であり、配布用Skillには含めず、実行時にも参照しません。
