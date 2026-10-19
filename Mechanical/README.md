# 独自設計の機構部品

この公開リポジトリには、本プロジェクトで設計したホルダー・電源支持部・圧入テスト片だけを含めます。**風洞本体は[株式会社ながれ技術研究所の公式MyWindTunnelページ](https://nagare-giken.jp/mywindtunnel/)からダウンロードしてください。** 原設計とその提供条件は公式サイトで確認してください。

## 公開する部品

| 部品 | 編集用STEP | 印刷用STL |
|---|---|---|
| 画面・基板のフレーム直付けホルダー | [Item Holder](cad/item_holder_contact_20261016/Item_Holder_FrameContact.step) | [1個](cad/item_holder_contact_20261016/Item_Holder_FrameContact_PRINT.stl) |
| 電源背面プレート | [PowerSupply Plate](cad/power_supply_printed_20261016/PowerSupply_Plate.step) | [型合わせ用1個](cad/power_supply_printed_20261016/PowerSupply_Plate_PLA_FITCHECK.stl) |
| 電源支持ブラケット | [2個配置の参照](cad/power_supply_printed_20261016/Printed_Supports_Pair.step) | [単体形状を2個印刷](cad/power_supply_printed_20261016/PSU_Support_PLA_FITCHECK_PRINT_2.stl) |
| M2インサート穴径確認片 | — | [2.8 / 2.9 / 3.0 mm](cad/item_holder_contact_20261016/Insert_Coupon_M2_2p8_2p9_3p0.stl) |
| M3インサート穴径確認片 | — | [4.5 / 4.6 / 4.7 mm](cad/item_holder_contact_20261016/Insert_Coupon_M3_4p5_4p6_4p7.stl) |

STEP 3件・STL 5件、合計8件です。結合アセンブリ、風洞本体、メーカー提供のねじ・電源・画面モデル、旧ZIPは同梱しません。STEPの製品名も単体のホルダー／プレート／支持部であることを確認しています。

## 組付けと安全

ホルダーはフレーム直付け、PLA、M3/M2熱圧入インサートを使う設計です。[寸法・部品・組立順序](cad/item_holder_contact_20261016/ASSEMBLY_AND_PARTS.txt)と[組付けマニュアル](../Docs/assembly/Item_Holder_Assembly_Manual.pdf)を参照してください。造形外形は272 × 256.4 × 13 mm。QIDI X-Plus 3ではブリムやパージ領域も含めスライサーで収まりを確認します。

電源支持部は**無通電での型合わせ用試作**です。[制限事項](cad/power_supply_printed_20261016/ASSEMBLY_AND_LIMITATIONS.txt)を先に確認してください。JC-360-12実機の穴・ねじ許容挿入長・重量・温度条件、PLAの強度・長期クリープ・電気安全は未確認です。適合するAC端子保護、抜け止め、保護接地は別途必要です。CAD上の非干渉だけで通電運用を承認しません。

これらのSTEP/STLは単体形状の出力であり、Fusionの全パラメトリック履歴や装置全体の組付けモデルではありません。ローカルの結合モデルは公開Gitへ追加しないでください。
