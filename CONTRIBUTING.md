# Issueベースの開発手順

ソフトウェア、回路、機構、測定を同じリポジトリで追跡する。現行製造版はPico Carrier Rev E。旧回路を現在の配線として使用しない。

## IssueからPRまで

1. 機能追加、不具合、測定・ハードウェア検証のいずれかでIssueを作成する。目的、変更範囲、受入条件、関連する設計版を明記する。
2. `main`から `feat/<issue番号>-<短い名前>`、`fix/...`、`docs/...` などのブランチを作成する。
3. 変更と検証結果を一つの目的にまとめてコミットする。例は `feat: add stability assessment (#12)`。
4. PRの `Closes #番号` でIssueと結び付け、模擬・実機・CFDのどれを検証したか記載する。
5. レビューと必要な検証が完了した後にマージする。Issueの記載だけで実機運転やファームウェア書込みが許可されたことにはならない。

初期候補は[ソフト開発優先順位](Docs/research/wind-tunnel-20261018/FEATURE_ROADMAP_2026-10-19.md)から、一つの機能と受入条件ごとに分ける。固定板の再設計は保留中。

## ローカル検証

Python 3.12で模擬テストを実行する。以下は実ファンを操作しない。

```powershell
cd software/control
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
New-Item -ItemType Directory -Path .runtime -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest -q tests --basetemp=.runtime/pytest-temp
cd ../..
.\software\control\.venv\Scripts\python.exe -m unittest discover -s tools/repository/tests -v
git add -- <変更したファイル>
.\software\control\.venv\Scripts\python.exe tools/repository/audit.py --staged
```

Linuxでは `.venv/bin/python` と `mkdir -p .runtime` を使用する。`--basetemp` のディレクトリはpytestが毎回消去するため、テスト専用の場所だけを指定する。実行DBなどを保存する `.runtime` 自体は指定しない。CIは同じPythonテストと、Git登録内容・回路依存ファイルの監査を実行する。SSH接続、実機運転、FW書込み、印刷、CFD計算はCIから実行しない。

`audit.py --staged` は作業ファイルではなくGitのステージ済み内容を確認する。50 MiB超、秘密情報の典型パターン、回路依存ファイル、資料リンクの大文字小文字を検査する。除外対象へのリンクはローカル専用として列挙する。パターン検査は秘密の不存在を保証しないため、差分と添付物も確認する。

PDFを含む初回送信前の追加点検には、pypdfを用意した環境で `python tools/repository/audit.py --staged --documents` を使用する。PDF画像内の文字やCAD内部メタデータの全面審査、ライセンス審査の代わりにはならない。

## 回路と機械設計の変更

- KiCadの `.kicad_pro`、`.kicad_sch`、`.kicad_pcb`、独自シンボル、フットプリント、ルールを一緒に管理する。Rev Eの原本は[Electronics](Electronics/README.md)から開く。
- KiCad 9系と標準ライブラリを基準とし、参照には`${KIPRJMOD}`またはKiCad標準変数を使用する。利用者PCの絶対パスをライブラリ参照へ追加しない。
- 回路変更ではERC、基板変更ではDRCと製造出力の差を確認する。保存済み検査結果を、新しい変更後の合格証拠として再利用しない。
- 製造用Gerber ZIPを変更する場合、元のPCB、BOM、組立・配線資料との対応をPRに示す。
- STEP/STLはGitへ含める。バイナリや大きいCADの更新が増えたら、初回履歴を増やし続ける前にLFSまたはリリース添付を検討する。
- Fusionクラウドの履歴と、保存したSTEP/STLは別物。Git内の出力だけでFusionの全パラメトリック履歴を復元できるとはみなさない。

## 証拠と秘密情報

実測データは原則変更せず、解析結果を別に保存する。新しい報告は `Docs/tests/<分野>/<日付と試験名>/` に、条件・元データ・検証範囲を記載する。生成した全場、実行環境、キャッシュはコミットしない。

パスワード、APIトークン、SSH秘密鍵、Wi-Fi認証設定、実行時DBをIssueやPRに添付しない。接続先に依存する情報は `.local` や環境変数へ置く。秘密を誤ってコミットした場合はpushを止め、まず資格情報を失効・変更する。ファイル削除だけでGit履歴から消えたとは考えない。

[Git管理範囲と初回push手順](Docs/operations/GIT_SETUP.md)も参照する。現時点でプロジェクト全体の公開ライセンスは選定していない。メーカー資料・部品画像・外部CADの権利を含め、公開範囲は別途判断する。
