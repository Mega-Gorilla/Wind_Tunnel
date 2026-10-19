# 固定板CFDのLinux比較環境

2026年10月19日。Docker Desktop 4.40.0 / Engine 28.0.4 / WSL2で動作確認。

## 確認した環境

- 配布元：OpenCFD公式 `opencfd/openfoam-run:2606`
- 固定したdigest：`sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb`
- Linux：Ubuntu 26.04 LTS、amd64、OpenFOAM Build `_481094f-20260618`
- OpenFOAM配置：`/usr/lib/openfoam/openfoam2606`
- Windows版と同じ `LSB;label=32;scalar=64`。保存済みバイナリ場の読み込みと並列実行を確認。
- Windows版のBuild表示は `34e226dfe3-20211220`。同じ2606表示でも同一実装とは扱わない。

解析データは本ディレクトリー内の `cases/linux_*` に保持する。Dockerのイメージと仮想ディスクは既存Dockerの標準保管先であり、Dドライブへ移設していない。

## 安全な起動範囲

`run_linux.py` は指定ケースのみを `/case` へbind mountする。ネットワーク無効、ポート公開なし、特権なし、Dockerソケットの共有なし。各コンテナーは終了時に削除されるが、Dドライブの解析結果は残る。メモリー上限8 GiB、CPUは明示した範囲へ固定する。

既存コンテナー3件は確認時に停止状態であり、手動で起動・停止・削除・再設定していない。今回の起動障害では、エンジンが起動していないことを確認してから今回起動したDockerプロセスを終了し、`%LOCALAPPDATA%/Docker/run` を `run.stale-20261019-windtunnel` に改名して残した。既存イメージ・コンテナー・設定を初期化していない。

## 再実行

ワークスペースのルート `D:/codes/Wind_Tunnel` で実行する。次は既存ケースの格子を検査する例で、ソルバーは起動しない。

```powershell
& 'analysis/plate_cfd_20261018/.venv/Scripts/python.exe' 'analysis/plate_cfd_20261019/run_linux.py' linux_F_urans 'checkMesh,-allTopology,-allGeometry' --ranks 8
```

流れの再計算は `system/controlDict` の `stopAt`、`endTime`、`writeInterval` を確認してから `pimpleFoam` を指定する。現在のケースは短時間診断用の終了時間で保存している。継続する場合は最新の保存時刻より先の終了時間を明示し、前回のログを上書きしない。

板ありLinuxの最終約0.01501秒はモニターのみで、全場の最終保存は初期チェックポイント0.01126998051秒。途中で終了時刻を短縮したため、全場保存周期に届かなかった。再開時はこの保存時刻からとなる。`prepare_linux.py` は今後の短時間試行では最初の保存周期を終了時刻に合わせるよう修正した。既存ケースをそのまま再実行すると `stopAt writeNow` により短時間で停止するため、意図する設定へ変更してから使う。

```powershell
& 'analysis/plate_cfd_20261018/.venv/Scripts/python.exe' 'analysis/plate_cfd_20261019/run_linux.py' linux_F_urans pimpleFoam --ranks 8
```

`prepare_linux.py` は別名ケースを作り、Windowsの元データを変更しない。ライブラリー拡張子をLinux用に変更し、統計場の保存をソルバーの保存時刻に限定する。継続初期場は `linux_clone_provenance.json` に記録する。定常反復150を非定常へ移す板なしケースでは、時刻を0へ付け直し、150秒とは扱わない。

## 既知の制限

拡張格子検査にはdeterminant警告が残る。`run_linux.py` が進行を許すのはその診断条件だけであり、全項目合格を意味しない。長時間計算、時間平均の採用、格子収束の確認は別の検証である。最初の板なし試行には分割数不一致による停止ログがあるが、4分割に修正後に格子検査とソルバー起動を確認した。

Linux用の初期ケースでは0.3秒を予定値として保存したが、短時間の性能確認に限定して終了時間を短縮した。実際の到達時間は `Docs/tests/cfd/2026-10-19_fixed_plate_refined/results/run_summary.json` と各ログを正とする。
