# 2026-10-19 固定板CFD再評価

報告先：[Docs/tests/cfd/2026-10-19_fixed_plate_refined](../../Docs/tests/cfd/2026-10-19_fixed_plate_refined)。前回の入力・結果は変更しない。

## 入力と実行環境

- 保存済みFusion v49のSTLを前回ディレクトリーから参照。CADの編集や実機操作は行わない。
- Pythonは `../plate_cfd_20261018/.venv/Scripts/python.exe`。同環境へGmsh 4.15.2を追加した。
- OpenFOAMは前回の作業フォルダー内のWindows版を使用。実際のバナーは `34e226dfe3-20211220 OPENFOAM=2606 version=v2606`。
- 同梱のMicrosoft MPI 10.1.12498.18を `tools` に展開。Microsoftの署名を確認した。OSへのインストール、サービス追加、他PCでの計算は行っていない。

## ファイル

- `mesh_section.py`：CAD断面に適合する2D格子。格子面積とCAD面積の一致を検査。
- `build_fitted.py`：断面から3D格子を押し出し、板厚部分のセルを除く。板あり／なしの配置を一致させる。
- `run_foam.py`：ローカル実行、実行コマンド・終了コード・所要時間の記録。各実行のログを別名で保存。
- `prepare_transient.py`：定常チェックポイントから、別フォルダーの物理時間t=0を作る。
- `prepare_axial_trial.py`：流れ方向の格子幅を変えた診断ケース。初期条件も変わるため純粋な格子収束試験ではない。
- `mesh_audit.py`：形状誤差、隙間の分割数、格子図。
- `analyze_runs.py`：実際のログ・モニターから数値を集計。予定値は結果にしない。
- `prepare_linux.py`・`run_linux.py`：公式Linuxイメージで別名ケースを実行。[環境と再実行方法](LINUX_ENVIRONMENT.md)。
- `report_figures.py`：格子検査、板厚方向の形状確認、実行時間、収束・25点比較の図。
- `validate_report.py`：終了ログ、25点数値、計算式、リンク、JSONの整合性を検査。科学的な精度認定とは別。
- `build_paper.py`：保存済み数値と図から2段組み5ページの論文形式PDFを生成。ReportLabとWindowsの明朝・メイリオを使用し、フォントを埋め込む。
- `validate_paper.py`：PDFのページ数、文字、主要数値、フォント、削除記録を検査。紙面はPopplerで全ページを画像化して別途確認。
- `cleanup_intermediates.ps1`：削除対象を限定した旧データ整理。既定は一覧のみ。`-Execute`は記録が既に存在すると停止し、再削除しない。
- `case_selection.json`：不合格試作・診断ケースの区別。
- `solver_trials.json`：最初の非定常試行の停止理由と設定変更。

## 再実行時の注意

生成コマンドは既存ケースを上書きしない。再生成は新しいラベルを指定する。`fitted_D/E` の実験的な構造化ストリップは面積検査に合格しておらず、採用しない。

PDF化後、不採用A/Cの`constant/polyMesh`とA/C/Dの断面格子を削除したため、これらの不採用ケースはそのまま実行できない。入力・採否・検査ログを参照し、必要なら別名で再生成する。Fの0.01秒と0.01126998051秒の間にある、平均量3ファイルだけの出力を削除した。初期場と全ての完全なチェックポイント、モニター時系列は保持した。[削除対象・サイズ・ハッシュ](../../Docs/tests/cfd/2026-10-19_fixed_plate_refined/results/cleanup_manifest.json)

`checkMesh -allTopology -allGeometry` のdeterminant警告を含むケースは、`mesh_diagnostic_acceptance.json` で条件を明記した診断実行に限る。警告がなくなったことや精度が保証されたことを意味しない。

定常反復数と非定常の秒を混同しない。URANSの瞬時変動はモデルで解像した変動であり、実測の乱れ強度そのものではない。圧力pは動圧単位の変数ではなく、圧力を密度で割った値（m²/s²）。Pa表示には1.2 kg/m³を乗じる。
