# Agent Skills

AIエージェントに任せる日々の作業を、再利用できるSkillとしてまとめる個人用リポジトリです。特定の分野に限定せず、実際に必要になったものから追加します。

リポジトリ名は当面 `agent-control-plane` のままです。大きな制御フレームワークや独自の認証基盤は作りません。

## 現在のSkill

| Skill | できること |
| --- | --- |
| [controlled-github](skills/controlled-github/SKILL.md) | Gitの状態確認、対象ファイルを限定したcommit、送信する全commitを確認したpush、push済みbranchからのPR作成 |
| [spec-driven-development](skills/spec-driven-development/SKILL.md) | 要求を仕様・受入基準・小さなタスクに整理し、依頼された範囲でテスト・実装・検証・引き継ぎを進める |
| [secret-checks](skills/secret-checks/SKILL.md) | ローカル環境と既存hookを診断し、秘密情報の検査hookを導入・検証・更新・切り戻し・解除・cleanupする |
| [codex-hardening](skills/codex-hardening/SKILL.md) | Codex CLIの版と設定を診断し、専用profileの導入・sandbox動作検証・復旧を行う |
| [claude-code-hardening](skills/claude-code-hardening/SKILL.md) | Claude Codeの設定をレビューし、調査用／開発用の設定候補を生成・照合する。実機での有効化確認は別手順 |

## 導入と使い方

使いたいSkillを `skills/` からフォルダごと、利用するエージェントが認識するSkillディレクトリへ配置してください。配置場所や呼び出し方法は利用製品の設定に従います。同名のSkillがある場合は、差分を確認してから更新してください。この作業で自動インストールは行いません。

各Skillは単独で利用でき、このリポジトリの他のファイルに依存しません。`controlled-github`にはGitとPython 3.10以上、PR操作には設定済みのGitHub CLIが必要です。`spec-driven-development`自体に追加ツールは不要で、開発先の既存ツールを使います。

`secret-checks`はLinux／WSL2、Git（`/usr/bin/git`）、Python 3.10以上、POSIX shellを対象とします。Python側の検査と導入管理は標準ライブラリだけで動き、画像用の外部ライブラリや専用Python環境は不要です。デフォルトのcombined版やGitleaks版では、[固定版ランナーの準備](skills/secret-checks/references/runner.md)が必要です。

### GitHubから導入する（Codex）

このリポジトリを手元にcloneせず、GitHubから取得して導入することもできます。Codexの`skill-installer`は他のGitHubリポジトリからの導入に対応しています。リポジトリ単位で使う場合の配置先は、導入先のルートにある`.agents/skills/`です。[OpenAI公式ドキュメント](https://learn.chatgpt.com/docs/build-skills)

導入先リポジトリでCodexを開き、次の依頼を送ってください。配布元は[main branchのskillsディレクトリ](https://github.com/DharmaDoll/agent-control-plane/tree/main/skills)です。

```text
$skill-installer

以下のGitHubリポジトリから、4つのSkillを導入してください。

repository: DharmaDoll/agent-control-plane
ref: main
paths:
- skills/spec-driven-development
- skills/controlled-github
- skills/secret-checks
- skills/codex-hardening

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

### codex-hardening クイックスタート

`codex-hardening`は、Codex CLIのバージョン・設定の競合を確認し、調査用／通常開発用の専用profileを管理します。既存の`config.toml`、認証、MCP、履歴は書き換えません。Skillを配置しただけでは設定は有効になりません。

参考にした[Codex CLI Hardening Cheatsheet](https://github.com/okdt/codex-cli-hardening-cheatsheet)の最小権限・人間の承認・実動作検証の方針を取り入れていますが、全設定の一括適用ではありません。keyringへの移行、Web検索、環境変数の継承、MCPの許可リスト、履歴・メモリの設定は変更しません。[対応範囲の比較](skills/codex-hardening/references/limitations.md#relationship-to-the-upstream-cheatsheet-checked-2026-11-03)を参照してください。

最初にprofileを手書きする必要はありません。組み込みのプリセットから用途を選び、環境に合わせて生成します。

#### profileの実体・保存先・名前

profileは名前を付けた設定のまとまりで、このSkillでは**専用のTOMLファイル**として保存します。`acp-development`はファイルパスではなく、起動時に指定するprofile名です。

| Skillで選ぶmode | 生成されるprofile名 | 保存先 |
| --- | --- | --- |
| `review` | `acp-review` | `<codex-home>/acp-review.config.toml` |
| `development` | `acp-development` | `<codex-home>/acp-development.config.toml` |

`<codex-home>`は、診断時に確認して管理scriptの`--codex-home`へ渡すCodexの設定ディレクトリです。例えば、それが`/home/user/.codex`なら、開発用の保存先は`/home/user/.codex/acp-development.config.toml`です。Skillの配置先である`.agents/skills/codex-hardening/`や、対象リポジトリ内に保存するという意味ではありません。OSのホームを指定する`--user-home`とも区別します。

**このSkillではprofile名は固定で、任意の文字列を指定する機能はありません。** 管理scriptに`--mode development`を渡すと、名前・保存先・ファイル内の権限定義を自動生成します。利用者が`config.toml`へ名前を登録したり、生成済みファイルを手で改名したりする必要はありません。生成は承認後の`apply`で行い、`inspect`や`plan`では保存しません。

#### PC上で追加・変更されるもの

例えばCodex homeが`~/.codex`で、開発用を選ぶ場合、承認後に次を管理します。

| ファイル・ディレクトリ | 役割 |
| --- | --- |
| `~/.codex/acp-development.config.toml` | 専用の権限設定。初回は追加、設定変更時はこの管理対象だけを更新 |
| `~/.codex/codex-hardening-state/` | 変更前後の生成設定、処理中の記録、排他ロック。復旧と変更検知に使用 |
| `~/.codex/rules/acp-hardening.rules` | 別途承認した場合だけ追加するコマンド制御。profile単位ではなく、このCodex home全体に影響 |

開発用profileでは、workspace内の編集を許可し、`.git`・`.agents`・`.codex`・`.aws`への書き込みを制限します。既定の認証情報パスへの読み書きと、Sandbox内コマンドのネットワーク通信を禁止し、承認が必要な操作は人間の判断に委ねる設定です。ログインシェルの使用も無効にします。読み取りをworkspace内だけに限定する設定ではありません。

別途導入するコマンドルールは、`sudo`の禁止、`rm`の承認要求、ルートやホームを対象とする一部の再帰削除形式の禁止です。あらゆる削除手段を防ぐものではありません。

既存の`config.toml`、Plugin、MCP、認証情報そのものやOSのファイル権限は変更しません。常駐監視ソフトも追加しません。profileは新しいCodexセッションで`codex --profile acp-development --cd /absolute/repository`と選択して使い、現在のセッションや通常起動の既定値を自動変更しません。

戻したい場合は管理scriptの`rollback`で前の生成設定へ戻し、`uninstall`でこのSkillの管理対象を取り除きます。profileと共通コマンドルールは別々に扱います。利用者が後から編集したファイルは勝手に上書きせず停止します。復旧後は新しいセッションで設定を読み直してください。設定の復旧は、既に起きた情報送信やファイル削除を取り消すものではありません。具体的な引数は[復旧手順](skills/codex-hardening/references/operations.md#recovery)を参照してください。

#### 1. 用途を選び、診断・計画を依頼する

| 用途 | 選ぶプリセット | 主な制限 |
| --- | --- | --- |
| 調査・レビュー | `review` | workspaceへの書き込み不可、コマンドの通信不可 |
| コード編集・ローカルテスト | `development` | workspaceは編集可能。保護対象のメタデータ、一般の一時領域への書き込み、コマンドの通信は制限 |

> codex-hardeningを使って、この環境を診断し、用途別プリセットを提示して。制限と変更内容を確認してから選びたい。まだ適用しないで。

用途が決まっていれば「開発用プリセットで計画して」と指定できます。通常は選んだ1種類だけを導入し、両方必要なら個別に計画・承認・検証します。どちらもクレデンシャル保護は既定で有効です。依存取得やpushなどが無条件に通る設定ではありません。

#### 2. 内容を確認して適用・検証する

診断が`BLOCKED`なら、適用へ進まず、表示された`review_details`と`next_steps`で互換性の確認対象を調べます。既知の設定項目名だけを表示し、値・plugin名・未知のキー名は公開しません。未知の項目は件数で示すため、必要なら手元で確認してください。既存設定を消して通すのではなく、対応可否を検証します。

`BLOCKED`でも設定案は参考表示されますが、`applicable: false`・`candidate_status: REFERENCE_ONLY`・`plan_id: null`となり、そのまま適用する計画ではありません。`READY`の計画を確認してから、次の依頼へ進みます。

> codex-hardeningを使って、確認済みの計画を適用し、許可範囲内の書き込みと、対象外の書き込み・通信の拒否を検証して。復旧方法と未検証事項も報告して。

#### 3. 新しいセッションでprofileを選ぶ

開発用の場合は、ターミナルから次のように起動します。`--profile`は既に生成したprofileの選択であり、新規作成や名前の設定ではありません。

```sh
codex --profile acp-development --cd /absolute/repository
```

導入後は、対象workspaceで選択先を再検証し、新しいセッションで `codex --profile acp-review --cd /absolute/repository` または `codex --profile acp-development --cd /absolute/repository` を指定します。既存セッションやグローバルの既定設定は変わりません。保護の例外を変更する場合は、そのprofileを再計画・承認・適用・検証します。他のPCの生成済みprofileはコピーせず、移行先で生成してください。共通のコマンド制御（`command-rules`）は別承認で、profileの切替では解除されません。

起動に使うCodexのインストールとCodex homeは、診断・検証したものに揃えてください。別のhomeや起動時の権限上書きを使う場合、同じ検証結果は流用できません。

#### 変更・切替・元に戻す

生成ファイルを直接編集せず、Skillに変更を依頼してください。管理対象ファイルの手動変更は不整合として停止する場合があります。

調査用へ切り替える：

> codex-hardeningを使って、このworkspaceでreviewプリセットを使いたい。未導入なら計画を作り、導入済みなら承認済みの例外を維持して再検証して。起動コマンドも提示して。

保護の例外を変更する：

> developmentのAWSパス保護だけを解除する計画を作って。他の保護は維持し、影響を説明して。まだ適用しないで。

例外は承認後に再適用・検証します。管理scriptでは`--disable-protection aws`などを使い、plan・apply・verifyに意図した例外の全リストを指定します。パス保護を解除しても、通信やクラウド側の操作権限まで許可されるわけではありません。

前の状態へ戻す／削除する：

> developmentの管理対象設定を前の状態に戻して。復旧後の検証状態も報告して。

> developmentの管理対象profileをアンインストールして。共通のコマンド制御は残して。

復旧には残っている管理記録を使います。profileと共通ルールは別管理で、片方の削除で他方は削除されません。具体的なCLI引数・保存される管理記録・cleanupは[操作・復旧手順](skills/codex-hardening/references/operations.md)を参照してください。

#### 対応環境と保護の範囲

デフォルト保護はLinux x86_64のCodex CLI **0.165.0・0.166.0**を対象とします。0.163.0・0.164.0の識別定義は残しますが、新しい保護を再検証するまで適用・検証は停止します。**Python 3.11以上**の標準ライブラリだけを使い、追加パッケージや専用Python環境は不要です。既存の3.11以上がなければ停止し、自動インストールはしません。WSL2は導入先で検証し、macOS・Windows・他の版を対応済みとは扱いません。

0.166.0では、`features.fast_mode`と一部の`tui`・`notice`設定を、型・件数・長さを検査したうえで保持できます。pluginの`enabled`とmarketplaceの既知メタデータも、存在だけでは停止しません。これらの実行・配布元の安全性は未検証として表示します。未知の権限項目・不正な型・権限競合は引き続き停止します。`tui.resume_cwd = "session"`も維持しますが、検証結果は指定workspace/profileを使う新規セッション向けであり、再開先には自動で引き継ぎません。詳しい[対応項目と理由](skills/codex-hardening/references/compatibility.md)を参照してください。既存設定を削除・無効化して通す処理は行いません。

更新に追従するため、安全方針と[互換性定義・更新手順](skills/codex-hardening/references/compatibility.md)を分離しています。未知の版や設定の競合では診断結果を返して適用を停止します。Codexや関連設定が変わったら再検証しますが、Codex本体の更新や常時監視は行いません。既存のproject設定・管理ポリシー・許可ルールなどがある環境は、初期版では追加レビューが必要になる場合があります。

0.164.0では、モデル・応答表示など5項目に限ってproject設定を保持したまま検査できます。権限の上書きや未検証の設定は引き続き停止します。開発用プロファイルも一般の一時領域への書き込みは許可していません。Goなどはタスク単位でworkspace内にキャッシュ・一時領域を明示する必要があり、詳しい実測結果は[検証記録](skills/codex-hardening/evals/validation.md)にまとめています。

profileは`<codex-home>/acp-review.config.toml`または`acp-development.config.toml`に配置され、新しいセッションで明示的に選択します。検証には一時ファイルとローカル接続を使い、モデルや外部サービスを呼びません。sandboxの起動失敗は拒否成功に数えません。Web・MCP・承認UI・ログ保存の安全性や秘密情報の読み取り防止は別の確認事項です。[操作・復旧手順](skills/codex-hardening/references/operations.md)と[制限事項](skills/codex-hardening/references/limitations.md)を参照してください。

認証情報の既知パスはデフォルトで読み書きを拒否します。AWS・Google Cloud・Azure・OCI・Kubernetesのほか、SSH、Docker、Terraform、Pulumi、Vault、GitHub/GitLabなど**21グループ・26パス**が対象です。認証情報の中身は読みません。`--user-home`でOSのホームを明示し、例外が必要なら利用者の承認を得て`--disable-protection aws`などを指定します。別の保存先・環境変数・OSの資格情報ストアまで保護するものではありません。

コマンド制御は別の`--mode command-rules`で管理します。`sudo`をdeny、`rm`をask、代表的なルート・ホーム削除をdenyとするルールを生成します。このrulesファイルは**同じCodex homeを使う他のセッションにも影響**するため、プロファイルとは別に計画・承認・適用します。既存rulesは上書きせず、対応するリテラル構文とCodex自身の判定を検証します。任意の削除処理を防ぐ保証や、すべての実行で確認画面が出る保証ではありません。[対象パス・opt-out・適用範囲](skills/codex-hardening/references/default-protections.md)を確認してください。

### Claude Code版のhardening

`skills/claude-code-hardening/`をフォルダごと、対象プロジェクトの`.claude/skills/claude-code-hardening/`、または個人用の`~/.claude/skills/claude-code-hardening/`へ配置すると、`/claude-code-hardening`で呼び出せます。[Claude Code公式のSkill仕様](https://code.claude.com/docs/en/skills)

> /claude-code-hardening この環境の設定と継承元を確認し、開発用の設定候補を作って。保護内容と変更先を示し、実機での有効化はまだ行わないで。

| 用途 | mode | 設定候補の意図 |
| --- | --- | --- |
| ファイルを読んで調査する | `review` | 編集・shell実行・委譲を拒否。shellを使うレビューやテストには不向き |
| コード編集・ローカルテスト | `development` | shellと編集に人間の承認を要求し、sandboxと資格情報パス保護を設定 |

Python 3.10以上の標準ライブラリだけで動くhelperが、`plan` → `export` → `verify`で候補JSONを生成・照合します。出力先はworkspace外の専用ディレクトリで、既存ファイルは上書きしません。`settings.json`や認証設定へ自動適用する機能はありません。

**初版は設定候補の生成・照合までを自動検証しています。Claude Code実機で検証済みの版はありません。** `ARTIFACT_MATCH`は生成内容との一致を意味し、sandboxの動作確認ではありません。既存設定の配列は結合されるため、空の許可リストを出力しても既存の許可は消えません。新しいセッションへの有効化には、版・設定の継承元・実際の拒否動作を確認します。[操作と有効化手順](skills/claude-code-hardening/references/operations.md)、[制限事項](skills/claude-code-hardening/references/limitations.md)

[okdt/claude-code-hardening-cheatsheet](https://github.com/okdt/claude-code-hardening-cheatsheet)も参考にしています。sandboxと権限ルールを重ねる方針を取り入れ、こちらではshellの自動承認や通信先の事前許可を既定に含めません。参照した版と採用判断は[出典・仕様の確認記録](skills/claude-code-hardening/references/sources.md)に記載しています。

helperのテストは使い捨てのローカルfixtureだけで実行できます。Claude本体・モデル・外部サービスは呼び出しません。

```sh
python3 -B -m unittest discover -s skills/claude-code-hardening/evals -p 'test_*.py' -v
```

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

Pythonスキャナは、主要サービスのトークン、JSON・`export`内の資格情報、認証情報入りURL、Basic認証ヘッダーも検査します。公開用キーと秘密キーを区別し、外部ライブラリやネットワーク照会は使いません。対象と制限は[検出ルール一覧](skills/secret-checks/references/python-rules.md)を参照してください。形式による検出なので、見逃し・誤検出はあり得ます。

Gitleaks方式の詳しい実行経路は、[Gitleaks hookとGoランナーの実行フロー](skills/secret-checks/references/gitleaks-hook-flow.md)にまとめています。GoへGitleaksをライブラリとして組み込む仕組み、入力ごとの分離、fragment処理、完了結果の照合、Dockerの実行・終了処理を説明しています。

新規導入はcombined／Dockerがデフォルトです。`pre-commit`と`commit-msg`はPythonのみ、`pre-push`はPython → Gitleaksの両方を実行します。画像のバイト数制限・大量投入制限は維持し、必須の検査で検出・検査不能・スキャナ欠落があれば拒否します。commit時にもGitleaksを使う場合は、導入・更新時に`--commit-gitleaks on`を指定してください。

既存環境の通常更新では現在の方式とcommit時の設定を保持します。旧combined環境を新方針へ切り替えるには、明示的に`--commit-gitleaks off`を指定します。Pythonが見逃した秘密情報はローカル履歴に入り得るため、公開前のpush検査とは保証が異なります。[combined方式の導入と制約](skills/secret-checks/references/combined.md)を確認してください。Skillをコピーしても既存hookは自動更新されません。

## 画像の拡張子・ヘッダー確認と大量公開の停止

PNG・JPEG・WebP・BMP・GIF・TIFF・HEICは、拡張子と先頭ヘッダーの識別情報を照合し、1件5 MiBまで許可します。不一致・空ファイル・識別に必要なバイト不足は拒否します。デコード・破損・画素数・フレーム／ページ数は検証せず、静止画像だけを許可する保証はありません。SVGは通常のテキストとして秘密情報を検査しますが、XML解析・描画・無害化はしません。

許可した画像の本文・メタデータには秘密情報検査やOCRを行いません。結果には許可件数と「内容は未検査」を表示します。ヘッダー照合は単純な取り違えを防ぎますが、先頭バイトの偽装や画像内の秘密情報までは防げません。標準ライブラリだけで動作し、外部画像ライブラリと専用Python環境は不要です。Gitleaksは引き続きDockerを優先します。既存hookは自動更新しません。

大量投入は、commitあたり追加・変更100ファイル／20 MiB、pushあたり新たに公開する500種類のblob／50 MiBを上限として停止します。commitはindexのファイル全体、pushは途中で削除された版を含む履歴を対象にします。既存のテキスト検査上限も維持します。新規branchのpushは到達可能な履歴全体を保守的に計上するため、大きな既存リポジトリでは停止する場合があります。

これは大量投入による事故を抑える制御であり、少量の個人情報、画像内の機密情報、分割した流出やWeb/API経由の変更まで防ぐものではありません。[許可拡張子・集計規則・制限事項](skills/secret-checks/references/images-and-publication.md)を確認してください。

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

`secret-checks`のPython版と導入管理のテストは、既存のPython 3.10以上と使い捨てのローカルGitリポジトリで実行します。画像用の追加パッケージは不要です。

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
