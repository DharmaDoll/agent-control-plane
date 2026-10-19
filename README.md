# Agent Skills

AIエージェントに任せる日々の作業を、再利用できるSkillとしてまとめる個人用リポジトリです。特定の分野に限定せず、実際に必要になったものから追加します。

リポジトリ名は当面 `agent-control-plane` のままです。大きな制御フレームワークや独自の認証基盤は作りません。

## 現在のSkill

| Skill | できること |
| --- | --- |
| [controlled-github](skills/controlled-github/SKILL.md) | Gitの状態確認、対象ファイルを限定したcommit、送信する全commitを確認したpush、push済みbranchからのPR作成 |
| [spec-driven-development](skills/spec-driven-development/SKILL.md) | 要求を仕様・受入基準・小さなタスクに整理し、依頼された範囲でテスト・実装・検証・引き継ぎを進める |

## 導入と使い方

使いたいSkillを `skills/` からフォルダごと、利用するエージェントが認識するSkillディレクトリへ配置してください。配置場所や呼び出し方法は利用製品の設定に従います。同名のSkillがある場合は、差分を確認してから更新してください。この作業で自動インストールは行いません。

各Skillは単独で利用でき、このリポジトリの他のファイルに依存しません。`controlled-github`にはGitとPython 3.10以上、PR操作には設定済みのGitHub CLIが必要です。`spec-driven-development`自体に追加ツールは不要で、開発先の既存ツールを使います。

依頼例：

> controlled-githubを使って、このworktreeのbranchと差分、commit・pushの前提を確認して。まだstage・commit・push・設定変更はしないで。

> controlled-githubを使って、合意した変更だけをcommitし、確認済みのremote・branchへpushして。認証設定は変えず、PRは作成しないで。

対象や権限が不明なら、書き込み前に確認します。「確認だけ」「commit」「push」「PR作成」は別の操作です。

開発の進め方を整える場合：

> spec-driven-developmentを使って、この機能の仕様・受入基準・実装計画・テスト計画を整理して。今回は提案までで、ファイルは変更しないで。

> spec-driven-developmentを使って、合意した計画をタスクごとに実装・検証して。結果と次の作業を既存の作業記録に残して。commit・pushはしないで。

小さな変更には短い確認だけを使い、複数工程の作業には[作業記録テンプレート](skills/spec-driven-development/assets/work-item.md)を必要に応じて使います。開発とGitHub操作のSkillは互いに独立しており、一方の利用がもう一方の操作許可になることはありません。

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

## 管理方針

READMEは日本語、Skillの指示・技術文書・コードは英語で管理します。英語が常に優れると断定するものではなく、指示の重複と翻訳のずれを避けるための運用方針です。

- 一つのSkillは一つの用途に絞り、単独で持ち出せるようにする。
- 手順はMarkdown、判断がぶれやすい検査は小さなscriptにする。
- 実際に必要になるまで共通frameworkや設定ファイルを増やさない。
- 実行した検証と、未検証の期待動作を分けて記録する。

共通ルールは[AGENTS.md](AGENTS.md)と[開発原則](docs/principles.md)にあります。旧GitHub文書のリンクは移行案内として残しています。`skills_plan/` は検討用の原案であり、配布用Skillには含めず、実行時にも参照しません。
