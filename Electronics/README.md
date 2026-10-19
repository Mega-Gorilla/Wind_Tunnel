# 電子回路とPico Carrier

現行の製作済み基板は **Pico Carrier Rev E** です。この公開版は独自の制御回路・基板・Pico FWを中心に収録し、旧版パッケージやPC固有の管理スクリプトは含めません。

- [Rev E KiCadプロジェクト](pico/pcb_rev_e/WindTunnel_Pico_Carrier_RevE.kicad_pro)
- [回路図](pico/pcb_rev_e/WindTunnel_Pico_Carrier_RevE.kicad_sch)・[PCB](pico/pcb_rev_e/WindTunnel_Pico_Carrier_RevE.kicad_pcb)
- [製造用Gerber ZIP](manufacturing/RevE/WindTunnel_Pico_Carrier_RevE_JLCPCB_Gerber.zip)
- [保存済みERC](pico/pcb_rev_e/erc.json)・[保存済みDRC](pico/pcb_rev_e/final_drc.json)
- [基板組立](../Docs/assembly/WindTunnel_Pico_Carrier_RevE_Assembly_Guide.pdf)・[センサーピン接続](../Docs/assembly/WindTunnel_RevE_Sensor_Pin_Guide.pdf)
- [Pico FWと診断コードの案内](pico/README.md)

ライブラリー、フットプリント、簡略モデルを同じフォルダー構成で保持しています。標準ライブラリーはKiCadで別途インストールしてください。KiCad由来の同梱ライブラリーには[公式ライセンス](library-licenses/KiCad-LICENSE.md)が適用されます。変更範囲と出典は[第三者資料の扱い](../THIRD_PARTY_NOTICES.md)を参照してください。

公開範囲の整理で回路・配線・銅箔・Gerberを変更していません。保存済みERC/DRCは過去の設計確認であり、将来の変更や製造・実装の合格を保証しません。
