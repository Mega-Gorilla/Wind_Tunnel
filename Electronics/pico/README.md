# Pico Carrier Rev Eとファームウェア

初代Raspberry Pi Pico（RP2040）を使用する現行構成。製造正本は[Rev E KiCadプロジェクト](pcb_rev_e/WindTunnel_Pico_Carrier_RevE.kicad_pro)です。旧Rev C/Dの接続図を現行の製造指示として使用しないでください。

- [回路図](pcb_rev_e/WindTunnel_Pico_Carrier_RevE.kicad_sch)・[基板](pcb_rev_e/WindTunnel_Pico_Carrier_RevE.kicad_pcb)
- [現行の制御ファームウェア](firmware/control_main.py)
- [基板組立](../../Docs/assembly/WindTunnel_Pico_Carrier_RevE_Assembly_Guide.pdf)・[センサーピン接続](../../Docs/assembly/WindTunnel_RevE_Sensor_Pin_Guide.pdf)
- [実機有限運転版の検証記録](../../Docs/tests/software/pico-control/README.md)
- [センサーとファンの段階試験](../../Docs/tests/fan-sensors/2026-10-17/TEST_RESULT.txt)

Picoがセンサー取得、Tach計数、PWM生成、通信断時の停止を担当し、PiとはUSBで接続します。FWとUI/APIの通信プロトコルを一致させて使用してください。停止専用の旧FWを現行制御版と混用しないでください。

`diagnostics` と測定記録内のスクリプトは試験用で、ファン駆動や保存済みFWの変更を伴うものがあります。内容確認のために実行せず、配線・電源・停止条件を確認してから使用します。センサー読値やTach換算RPMの機能確認は、風速・回転数の独立校正ではありません。

外部12 V、Pi給電、PicoのUSB・3.3 Vを混同しないでください。SW1はファン電源の手動スイッチで、安全認証された非常停止ではありません。初回配線・保守は無通電で行い、運転時はファン周囲を保護します。
