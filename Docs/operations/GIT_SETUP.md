# Git管理範囲と初回push

既定ブランチは `main`。公開対象は独自の回路・ソフトウェア・追加固定部品と検証資料です。[公開準備記録](../maintenance/publication-review/README.md)と[第三者資料の扱い](../../THIRD_PARTY_NOTICES.md)を確認してください。

## 公開範囲

- 公式配布の風洞CAD、公式形状を含む結合モデル・変換データは配布しません。本体は[MyWindTunnel公式サイト](https://nagare-giken.jp/mywindtunnel/)から取得します。
- 独自部品の単体CAD、現行回路・PCB・Gerber・FW、UI/API、独自の図・測定結果・調査報告を含めます。
- CFDコード・設定は含めますが、元の形状、格子、全計算場、実行環境はローカルで別途準備します。cloneだけでは過去の計算を再開できません。
- 接続情報、認証情報、実機管理ログ、個人情報を含む整理記録、外部ツール、キャッシュは除外します。
- 除外はGit管理からの除外です。元ファイルはローカルに保持し、Gitだけをバックアップ先にしません。

`.gitignore` は未登録ファイル向けです。登録済みファイルや過去コミットから情報を消す機能ではありません。初回公開前の履歴も確認してください。

## 追加・更新時の確認

```powershell
git diff --cached --stat
python tools/repository/audit.py --staged --public
python tools/repository/audit.py --staged --public --documents
python -m unittest discover -s tools/repository/tests -v
```

PDFのテキスト抽出にはpypdfが必要です。上記に加え、[CONTRIBUTING](../../CONTRIBUTING.md)の模擬テスト、画像・CADの目視確認、コミット作者メールの確認を行います。機械検査は秘密情報の不在や権利の適法性を保証しません。

Git内の文書パスは `Docs` です。Windowsで既存の表示名が `docs` の場合も、追加後に `git ls-files` で登録漏れ・大文字小文字を確認してください。

改行は `.gitattributes` で管理します。測定生データ・製造ファイルのバイト列を維持し、PDF・画像・ZIP・STLはバイナリ扱いです。大容量の計算場は入れず、監査の上限を50 MiB/ファイルとします。

## GitHubリポジトリとpush

2026-10-19、[Mega-Gorilla/Wind_Tunnel](https://github.com/Mega-Gorilla/Wind_Tunnel)を公開設定で作成し、ローカルの `origin` に登録した。作成確認時点では空のリポジトリで、初回pushは未実施。

公開リポジトリの作成と、ローカル内容の送信は別の操作です。送信先・公開範囲を再確認してから、承認されたブランチだけをpushします。ローカルの復旧用履歴を公開する `--mirror` は使いません。

```powershell
git remote -v
git log --format=fuller -1
git status --short
git push -u origin main
```

このコードブロックは手順であり、自動実行指示ではありません。originが未設定なら、確定したGitHub URLを登録してください。既存originを確認なしに上書きしないでください。

初回push後にIssueフォーム、PRテンプレート、CIの表示・実行を確認します。テンプレートは機能改善・不具合・測定検証の3種類です。推奨運用はIssueに目的と受入条件を記し、PRで変更し、CI成功を確認することです。

## 参考

- [GitHubのコミットメール設定](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address)
- [GitHubの大容量ファイル](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
