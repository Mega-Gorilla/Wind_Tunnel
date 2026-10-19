# Raspberry Piの実測UI配備と運用

2026年10月17日

Raspberry Pi 3 B+に実機有限運転版を配備した際の運用記録です。接続先IPとSSHユーザーはローカル設定で管理し、この公開資料には含めません。Picoの `0.3.0-control` とUSB通信し、Tach由来の推定RPM、温湿度・気圧・差圧・電圧・電流・電力を表示します。画面からPWM 0または20～100%、最大300秒の試験を実行できます。風速は未校正なので表示しません。

## 画面を使う

デスクトップログイン時にFirefoxが全画面で起動します。通常は「実測・実機制御」「実Pico · 2 Hz」と表示します。初期状態は停止待機・遠隔OFFです。上部の停止ボタンは実行中の試験を中止し、遠隔許可を取り消します。停止応答と惰性回転によるRPM低下は別に確認します。

画面は800×480です。既存の180度回転とタッチ補正は変更していません。ブラウザー内のポインター操作を自動検証しましたが、指で触れたときの位置・感触は本体で確認してください。

中央領域を上下にスワイプしてスクロールできます。数値欄はテンキー、文字欄は英数字・記号キーボードを開きます。上部の停止と下部ナビゲーションは固定です。labwcの既存の `mouseEmulation="yes"` を維持し、アプリ側でドラッグをスクロールに変換します。入力欄やコピー用テキストからのドラッグは通常の編集に残します。[操作例と検証記録](../../../../Docs/tests/software/touch-ui/README.md)

本体セッションは有効な生存確認に合わせて更新されます。遠隔ONは時間無制限ですが、画面通信断・異常・停止・再起動でOFFになります。表示を閉じた後はSSHから次でアプリを開き直せます。

```sh
systemctl --user restart windtunnel-kiosk.service
```

画面を閉じてデスクトップへ戻す場合は、次を使います。

```sh
systemctl --user stop windtunnel-kiosk.service
```

## 配置と起動構成

| 項目 | Pi上の場所・設定 |
|---|---|
| 実行ユーザー | 配備先の非rootユーザー |
| 配備版 | `~/windtunnel-control/releases/20261017-touch-ui-01` |
| バックエンド指定 | `windtunnel-kiosk.service.d/monitor.conf` の `WT_BACKEND=pico-control` |
| 実行先リンク | `~/windtunnel-control/current` |
| ユーザーサービス | `~/.config/systemd/user/windtunnel-kiosk.service` |
| デスクトップ自動起動 | `~/.config/autostart/windtunnel-kiosk.desktop` |
| 模擬履歴DB | `~/.local/share/windtunnel-control/simulation/simulation.sqlite3` |
| 実測版設定DB | `~/.local/share/windtunnel-control/monitor/monitor.sqlite3`。模擬履歴は混入しない |
| 専用Firefoxプロファイル | `~/.local/share/windtunnel-control/firefox` |
| サービスログ・検証記録 | `~/windtunnel-control/evidence/` |
| ブラウザーログ | `~/.local/share/windtunnel-control/monitor/firefox.log` |
| API待受 | `127.0.0.1:8765` のみ |

`kiosk.py` がサーバーと専用ブラウザーの子プロセスを管理します。サーバー異常終了時はブラウザーも終了し、サービスが新しい認証情報で再起動します。ブラウザーを正常終了した場合はサービスも停止します。他のブラウザーやデスクトップは終了させません。

起動時の一回限りの認証情報は所有者専用のローカルファイル経由で渡し、コマンドライン引数に載せません。履歴・プロファイル・ローカル認証ファイルは共有しないでください。診断用の9222番ポートは通常運用では開きません。

LAN向けAPIは未公開です。「遠隔ON＋許可IP＋APIトークン」の判定は実装済みですが、LAN上のLLMクライアントから直接接続するにはTLSと公開範囲の整備が必要です。

## 依存関係と再配備

PiはRaspbian 13 armhf、Python 3.13.5を使用します。OSのパッケージ管理で次を導入しました。システムPythonにpipで上書きしていません。

```sh
sudo apt-get install --no-install-recommends python3-fastapi python3-uvicorn python3-venv python3-pytest python3-httpx python3-websocket
```

検証した主要パッケージはFastAPI 0.115.11-4、uvicorn 0.32.0-3、Pydantic 2.10.6-2、pydantic-core 2.27.2-3です。全記録は `test-results/pi-packages.txt` に保存しています。`python3-websocket` は診断用で、通常の表示には使用しません。

再配備時は `~/windtunnel-control/releases/` 内の新しいディレクトリーへ `windtunnel`・`tests`・`deploy` を転送し、そこで `python3 -m pytest -q tests/test_api.py` を実行します。合格後に `sh deploy/pi/install-user.sh` を実行してください。既存のサービス・自動起動ファイルと旧リリースへのリンクは `~/windtunnel-control/backups/` へ保存されます。履歴DBはリリースと分離しており、再配備では削除しません。

## 表示方式と制約

このPiではChromium 149の描画プロセスが高負荷となり、UIが画面に描画されませんでした。Wayland・XWayland・GPU無効化を試しても解消しなかったため、導入済みのFirefoxで全画面表示を検証しました。Chromium自体やOS全体の描画設定は変更していません。Firefoxは専用プロファイルでソフトウェア描画を使い、サンドボックスを無効化していません。

初回起動は画面が出るまで時間がかかることがあります。SDP810は取得開始後5秒の安定待ちを表示します。長時間運用でのメモリ・ログ容量、物理タッチ操作感は引き続き評価対象です。現在の全画面表示は、OSへのアクセスを防ぐセキュリティ専用端末設定ではありません。

模擬版0.1.0の配備時はPi全体の再起動後の自動表示を確認しました。そのときの短時間測定は全コア合計CPU使用率7.2%、使用可能メモリ455 MiB、swap使用0 MiB、SoC温度52.6℃でした。これは実測版の負荷測定値ではありません。一時的なsoft temperature limit到達の履歴があるため、長時間運用前にPiの冷却状態も確認してください。[過去の検証記録](../../VERIFICATION.md)

Pico常駐計測とUSB通信の仕様・証跡は[実機有限運転版](../../../../Docs/tests/software/pico-control/README.md)を参照してください。実機で使うpyserialはOSの `python3-serial` を利用します。シリアル診断スクリプトを同時実行せず、先にkioskサービスを停止してください。WDTは最初の運転許可後から再起動まで有効です。保守でraw REPLを長時間使う場合は、停止確認後にprotocol 2のrebootで再起動し、WDTが未始動の状態で作業します。運転中のREPL操作は禁止です。

0.2.0停止専用アプリとPicoの旧main.pyは保持しています。旧アプリだけへリンクを戻してもprotocol 2とは通信できないため、ロールバックはPico FWとバックエンドを対で行います。設定・履歴DBは削除しません。

実装時に参照した公式資料：[Raspberry Piのkiosk設定](https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/)、[Firefox kiosk mode](https://support.mozilla.org/en-US/kb/firefox-enterprise-kiosk-mode)、[Firefoxの検証用BiDi接続](https://developer.mozilla.org/en-US/docs/Web/WebDriver/How_to/Create_BiDi_connection)。
