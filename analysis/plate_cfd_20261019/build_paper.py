"""Five-page, two-column Japanese paper from saved CFD evidence; no solver I/O."""
from pathlib import Path
import json
from xml.sax.saxutils import escape
from PIL import Image as PILImage
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle, Image, Frame, Spacer

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT/'Docs/tests/cfd/2026-10-19_fixed_plate_refined'
OUT = REPORT/'WindTunnel_FixedPlate_CFD_Paper_2026-10-19.pdf'
FIG = REPORT/'figures'
DATA = REPORT/'results'
run = json.loads((DATA/'run_summary.json').read_text())
snap = json.loads((DATA/'snapshot_comparison.json').read_text())
quality = json.loads((DATA/'mesh_quality.json').read_text())

pdfmetrics.registerFont(TTFont('JPSerif', 'C:/Windows/Fonts/msmincho.ttc'))
pdfmetrics.registerFont(TTFont('JPSans', 'C:/Windows/Fonts/meiryo.ttc'))
W,H = 210*mm,297*mm
M,G = 16*mm,7*mm
FULL=W-2*M
CW=(FULL-G)/2
INK=colors.HexColor('#17232D')
BLUE=colors.HexColor('#24556C')
GREY=colors.HexColor('#59656E')
STYLES={
 'body':ParagraphStyle('body',fontName='JPSerif',fontSize=9.2,leading=14.2,wordWrap='CJK',spaceAfter=7,textColor=INK),
 'head':ParagraphStyle('head',fontName='JPSans',fontSize=10.8,leading=16,wordWrap='CJK',spaceBefore=6,spaceAfter=6,keepWithNext=True,textColor=INK),
 'small':ParagraphStyle('small',fontName='JPSerif',fontSize=8.2,leading=12.1,wordWrap='CJK',spaceAfter=6,textColor=INK),
 'caption':ParagraphStyle('caption',fontName='JPSerif',fontSize=8.2,leading=12,wordWrap='CJK',spaceAfter=7,textColor=INK),
 'cell':ParagraphStyle('cell',fontName='JPSerif',fontSize=8.2,leading=12,wordWrap='CJK',textColor=INK),
 'th':ParagraphStyle('th',fontName='JPSans',fontSize=8.1,leading=12,wordWrap='CJK',textColor=INK),
 'title':ParagraphStyle('title',fontName='JPSans',fontSize=18,leading=26,alignment=1,spaceAfter=9,textColor=INK),
 'center':ParagraphStyle('center',fontName='JPSans',fontSize=8.8,leading=13.5,alignment=1,spaceAfter=8,textColor=INK),
 'abstract':ParagraphStyle('abstract',fontName='JPSerif',fontSize=9.2,leading=14,wordWrap='CJK',spaceAfter=7,textColor=INK),
}
def p(s,style='body'):
    return Paragraph(escape(str(s)).replace('\n','<br/>'),STYLES[style])
def h(s):return p(s,'head')
def cap(s):return p(s,'caption')
def table(headers,rows,width=CW,fractions=None):
    fractions=fractions or [1]*len(headers)
    t=Table([[p(x,'th') for x in headers]]+[[p(x,'cell') for x in row] for row in rows],
            colWidths=[width*f/sum(fractions) for f in fractions],hAlign='LEFT')
    t.setStyle(TableStyle([
        ('LINEABOVE',(0,0),(-1,0),.7,INK),('LINEBELOW',(0,0),(-1,0),.45,INK),
        ('LINEBELOW',(0,-1),(-1,-1),.7,INK),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),
        ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
    ]))
    return t
def img(name,width=FULL):
    with PILImage.open(FIG/name) as im: w,hh=im.size
    return Image(str(FIG/name),width=width,height=width*hh/w)

c=canvas.Canvas(str(OUT),pagesize=(W,H),pageCompression=1)
c.setTitle('小型吸込型風洞のピトー管固定板に関するCFD再評価')
c.setAuthor('WindTunnel Project')
c.setSubject('形状適合格子と短時間非定常解析による診断評価。校正用補正値は未確定。')
def header(num,label):
    c.setFillColor(BLUE);c.setFont('JPSans',7.2)
    c.drawString(M,H-11*mm,'WINDTUNNEL  /  CFD TECHNICAL PAPER')
    c.drawRightString(W-M,H-11*mm,label)
    c.setStrokeColor(GREY);c.setLineWidth(.4)
    c.line(M,H-14*mm,W-M,H-14*mm);c.line(M,15*mm,W-M,15*mm)
    c.setFont('JPSans',7);c.setFillColor(GREY)
    c.drawString(M,10*mm,'2026-10-19  |  技術調査報告・未査読  |  数値解析（実測ではない）')
    c.drawRightString(W-M,10*mm,f'{num} / 5')
def frame(items,x,bottom,width,top,name):
    todo=list(items)
    f=Frame(x,bottom*mm,width,(top-bottom)*mm,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0,id=name)
    f.addFromList(todo,c)
    if todo:raise RuntimeError(f'Layout overflow {name}: {len(todo)}; {getattr(todo[0],"text",type(todo[0]).__name__)}')
def columns(left,right,bottom,top,name):
    frame(left,M,bottom,CW,top,name+'L')
    frame(right,M+CW+G,bottom,CW,top,name+'R')

header(1,'目的・解析方法')
frame([
 p('小型吸込型風洞のピトー管固定板に関する\nCFD再評価','title'),
 p('形状適合格子の改善と短時間非定常解析による診断\nWindTunnel Project　／　保存モデル merged model v49','center'),
 p('要旨　ピトー管を格子状に位置決めする固定板について、一定流量条件で上流の25点速度と必要入口静圧への影響を検討した。CAD断面に沿った格子により閉塞率の再現と非凸セルの問題は改善した。一方、細長いセルに関する検査不合格は残った。定常解析に加えてWindows版と公式Linux版OpenFOAMで非定常計算を実行したが、到達時間は最大約0.015秒であり、初期過渡を除いた統計値は得られていない。診断用スナップショットの差は校正値とせず、局所3次元格子・時間刻み・統計定常性・実機比較を次段階の検証とする。','abstract'),
 p('キーワード：小型風洞、固定板、閉塞、CFD、格子品質、URANS、数値検証','small'),
],M,211,FULL,278,'title')
columns([
 h('1. 目的と評価範囲'),
 p('本報告の目的は、固定板の有無が上流の測定位置に与える影響を、同じ流量で比較できるか検証することである。対象は数値解析であり、差圧センサー、Raspberry Pi、オシロスコープの実測データではない。'),
 p('評価量は、板前面から約55 mm上流の25点における流れ方向速度と、流量を維持する入口静圧である。同じPWM・回転数での風量低下、あるいはピトー管の指示誤差を直接求めるものではない。'),
 h('2. 形状と境界条件'),
 p('流路の外接寸法は80 mm角であるが、角部を除くCAD断面積は6,271.168 mm²である。板厚5 mmの中央断面を押し出し、25個のφ4.2 mm穴、大きな格子開口、周縁の公称0.2 mm隙間を表現した。'),
 p('板の流路投影面積は2,168.574 mm²、閉塞率は34.5801%である。これは面積の比であり、風量低下率ではない。板厚方向5断面を確認し、中央断面との差は最大0.396 mm²だった。全面的な3D形状一致を保証する検査ではない。'),
 h('2.1 比較量の限定'),
 p('速度は流れ方向成分Uyを採用した。流路断面の平均速度3 m/sと、境界層の影響を受ける個々の点の値は一致するとは限らない。板なしの同座標の値を比較の基準とする。'),
 p('25点の配置は既存の5×5格子に合わせたものであり、この点数だけで壁際を含む断面積分や乱れの分布を十分に表せると認定したものではない。'),
], [
 cap('表1　共通の計算条件。流量は実流路面積から算出。'),
 table(['項目','条件'],[
 ['計算領域','一定断面、長さ400 mm'],['流入','一様3.0 m/s、約67.73 m³/h'],
 ['空気','ρ=1.2 kg/m³、ν=1.5×10⁻⁵ m²/s'],
 ['乱流条件','流入乱れ強さ1%、長さ5 mm'],['モデル','非圧縮、k-ω SST、壁はno-slip'],
 ['比較位置','y=-55.053 mm、x,z各-32,-16,0,16,32 mm'],
 ['圧力基準','出口静圧0、入口は面積平均'],
 ],fractions=[26,74]),Spacer(1,5),
 p('流れは+y方向、板前面をy=0、流路中心をx=z=0とする。比較面はCADのプローブ先端外形を基準とし、現物の全圧孔・静圧孔との一致は未確認である。','small'),
 p('ファン、収縮胴、ディフューザー、整流材、プローブ本体、供試模型、印刷面粗さは含めない。したがって実機全体の流速を予測するモデルではない。','small'),
 h('2.2 数値検証の判断軸'),
 p('検証は、形状の再現、格子品質、反復収束、時間統計の安定、空間・時間刻み依存性、実測との一致を分けて行う。保存ファイルの整合性が合格しても、これら全てが検証されたことにはならない。'),
 p('本書では未達の項目を残したまま精度の数値を宣言しない。運転用補正を追加する前に、目的とする許容誤差を決め、それを下回る差で比較量が安定することを確認する。'),
],21,208,'p1')
c.showPage()

header(2,'格子の検証')
frame([h('3. CAD断面への適合と格子品質'),img('mesh_detail.png'),
 cap('図1　Gmshで生成した形状適合格子[1]。左：全断面、中央：小穴、右：周縁隙間の拡大。橙は板、薄青は流路。隙間を10本の線で監査し、公称0.2 mm幅に2セルが存在することを確認した。')],M,194,FULL,278,'p2fig')
frame([cap('表2　前回の選択格子と今回の格子F。閉塞率誤差はCAD値との差。'),
 table(['指標','前回（細かい格子）','今回（格子F）'],[
 ['板あり／板なしセル数','510,642 / 277,714','1,060,170 / 1,127,951'],
 ['閉塞率／CADとの差','約35.510% / +0.930ポイント','34.580163% / +0.000103ポイント'],
 ['最大非直交角／skewness','59.69° / 3.59','49.62° / 1.35'],
 ['非凸セル','20,080','検査合格'],
 ['最大アスペクト比','6.91','491.01'],
 ['小さいdeterminantのセル','検査合格','238,220（板あり）'],
 ['拡張格子検査の全項目合格','いいえ','いいえ（1項目不合格）'],
 ],width=FULL,fractions=[36,30,34])],M,111,FULL,191,'p2table')
columns([
 h('3.1 改善した点'),
 p('閉塞率の誤差と非凸セルを改善し、旧格子で表せなかった周縁隙間を流路として残した。体積・面・補間重み等の検査も通過したため、条件付きの診断計算を行った。'),
 p('ただし面積の数値的一致は、速度の精度や現物の製作精度を意味しない。2セルで隙間流れを十分解像できることも確認できていない。'),
 h('3.2 残存する問題'),
 p('細い断面格子を400 mm全長へ押し出す構成により、高いアスペクト比とdeterminant警告が残った。また小穴近傍は約1 mmで、旧局所格子の約0.5 mmより粗い部分がある。'),
],[
 h('3.3 「細分化」と「収束」の区別'),
 p('格子Fは格子Bと同じ断面を用い、軸方向幅を最小0.1→0.5 mm、最大16→12 mmへ変更した。初期場もセル番号に沿って伸縮したため、BとFの差を純粋な格子誤差とはみなさない。'),
 p('セル数の増加だけで全面的な高解像度化とは言えない。次は板・穴・壁・隙間近傍のみを細かくする3次元格子へ変更し、形状と初期化を揃えた系統的な空間収束試験を行う[3]。'),
 p('格子A/Cは不採用、D/Eは断面面積不一致で中止した。採否理由・検査ログは保持し、不採用の大容量生成データは整理対象とした。','small'),
],21,123,'p2')
c.showPage()

header(3,'反復と物理時間の区別')
frame([h('4. 定常計算と短時間非定常計算'),img('convergence_diagnostics.png'),
 cap('図2　収束診断。左上のみ横軸はSIMPLEの反復回数であり、秒ではない。他の3図は非定常の物理時間。橙はWindows格子Fの保存場からLinuxへ継続した計算、緑の板なしは別の初期場である。異なる履歴の曲線を同時測定や一致した平均期間として比較しない。')],M,137,FULL,278,'p3fig')
columns([
 h('4.1 数値解法と実行条件'),
 p('定常計算はSIMPLE、非定常計算はPIMPLEと後退差分を用いた。PIMPLEは外側1回、圧力補正2回とし、診断設定の目標最大Courant数は2とした。保存ログでは過渡的に2を超える値もあり、時間刻み独立性は未確認である。'),
 p('初回の格子B非定常試行では厳しい圧力最終解法が1,000反復の上限に達したため中断した。その後、セル並べ替えと圧力解法の許容値を見直し、短時間の計算を完了した。これを物理的不安定性の証明とはしない。'),
 cap('表3　主要試行の末尾値。全て未収束診断値。'),
 table(['条件','到達時間等','入口静圧'],[
 ['F・板なし定常','150反復','1.541 Pa'],
 ['F・板ありWindows',f"{run['fitted_F_urans']['last_monitor_time_or_iteration']:.5f} s",'8.696 Pa'],
 ['F・板ありLinux',f"{run['linux_F_urans']['last_monitor_time_or_iteration']:.5f} s",'8.758 Pa'],
 ['F・板なしLinux','0.00200 s','1.384 Pa'],
 ],fractions=[42,31,27]),
],[
 h('4.2 保存則と解の収束は別問題'),
 p('格子F・板ありWindows末尾の入口と出口の流量不一致は0.0000869%だった。質量保存は改善したが、それだけで速度分布や圧力が正しいとは判定できない。板なし基準も厳しい残差目標には未達だった[2]。'),
 p('400 mmを3 m/sで通過する時間は0.133秒であり、今回の最大約0.015秒はその約11%にすぎない。初期過渡を除いた統計が得られたとは言えず、0.133秒を超えること自体も十分条件ではない。'),
 p('定常反復の振動を渦放出周期に換算しない。URANSの速度変動はモデルで解像した成分であり、そのまま実測の乱れ強さとはならない。時間平均は物理時間で評価し、複数の平均窓の安定性を別途確認する[4]。'),
 h('4.3 最終3D場の保存範囲'),
 p('Linux板ありの0.01501秒では、ログ・25点・入口静圧・流量は保存済みだが、3D全場は未保存である。次頁の速度分布図と再開用全場はWindowsの0.01127秒を使用した。'),
],21,133,'p3')
c.showPage()

header(4,'速度場の比較と解釈')
frame([h('5. 25点速度と固定板近傍の瞬時場'),img('grid25_startup_comparison.png'),
 cap('図3　同じ格子F・同じ25座標の診断比較。左：板なし定常150反復、中央：板あり非定常0.01127秒、右：各点の速度比差。タイルは点の配置を示し、領域平均ではない。速度の色尺度を共通化して表示した。')],M,188,FULL,278,'p4grid')
frame([img('axial_startup.png'),
 cap('図4　板あり0.01127秒の中心縦断面。流れは右向き、破線は比較面、灰色は板またはサンプル欠落位置。板下流の速度むらは瞬時の診断結果であり、平均流れや渦放出周波数の確定図ではない。')],M,112,FULL,187,'p4axial')
lo,hi=snap['point_difference_range_percent']
columns([
 h('5.1 差分の定義と数値'),
 p('各点の流れ方向速度をUとし、診断差分を次式で計算した。'),
 p('δ(i) = 100 × (U板(i) / U無(i) - 1) [%]　(1)','center'),
 p(f'今回のスナップショットではδの範囲は{lo:.2f}～+{hi:.2f}%、入口静圧増分は{snap["additional_inlet_static_pressure_snapshot_Pa"]:.2f} Paだった。ただし、異なる初期履歴・未収束状態の差であり、「板で最大2.54%遅くなる」という確定結果ではない。'),
 p('前回の細かい格子の診断差は約-0.315～+0.317%、入口静圧増分は約8.00 Paだった。今回との違いには格子、初期過渡、解法が混在する。どちらも小さい影響率を保証する補正値として採用しない。'),
],[
 h('5.2 圧力の意味'),
 p('OpenFOAMのpは圧力を密度で割った量（m²/s²）であり、ρ=1.2 kg/m³を掛けてPaに換算した。比較値は同一流量を保つ入口静圧の増分である。出口の運動エネルギー流束補正を含む厳密な全圧損失ではない。'),
 p('したがってピトー差圧から7.15 Paや8 Paを差し引く補正は行わない。Linux末尾の板あり・なしの差も、同じ平均期間の値ではないため確定値として採用しない。'),
 h('5.3 実機校正への扱い'),
 p('閉塞条件は校正と使用時で合わせる必要がある[5]。当面は固定板を取り付けた状態で校正・運転し、板なし校正を自動転用しない。制御ソフトへのCFD由来の風速補正追加は行っていない。'),
],21,109,'p4')
c.showPage()

header(5,'考察・結論・文献')
columns([
 h('6. Linux比較と計算コスト'),
 p('公式opencfd/openfoam-run:2606をdigest固定で導入し、格子検査と継続計算を確認した[6]。WindowsとLinuxは共に2606表示だが、Buildはそれぞれ34e226dfe3-20211220と_481094f-20260618であり、同一実装ではない。'),
 p('同じ格子B初期場の最初の6ステップはWindows約93秒、Linux約78秒だった。ただし到達物理時間、MPI、Build、計算負荷が異なるため、OSだけの速度差とは断定できない。Linux格子F継続は物理時間約0.00374秒に約765秒を要した。'),
 p('Linux化のみでは格子品質や計算時間の課題を解消できなかった。細かい断面を全長へ押し出す方式を先に見直すことが合理的である。'),
 h('7. 次段階の検証'),
 p('①局所3次元格子：板・穴・隙間近傍を細分化し、遠方を粗くする。同じ形状と境界条件で段階的な格子比較を行う[3]。'),
 p('②統計定常性：初期過渡を除き、板あり／なしで等しい評価期間を確保する。連続した複数時間窓で25点速度と入口静圧の平均を比較する。'),
 p('③時間刻み：半分の時間刻み等で平均量の変化を確認する。目標Courant数だけで時間精度を認定しない。'),
 p('④実物確認：印刷後の周縁隙間と測圧孔位置を確認する。独立支持したプローブで板あり／なしを測り、同じ基準流速と同じPWMの比較を分ける。'),
 h('8. 結論'),
 p('形状適合格子によって閉塞率の再現と非凸セルは改善したが、格子品質・空間依存性・時間依存性・統計定常性・実測照合の検証が残る。固定板の流速影響率と補正値は未確定である。今回の成果は、影響が小さいことの証明ではなく、次の検証に必要な問題の切り分けである。'),
], [
 h('データの追跡性と保存方針'),
 p('本書の図表は保存済み解析データから作成した。今回の文書化に伴う実機操作・追加のCFD計算は行っていない。表示桁数は数値出力の丸めであり、測定精度や不確かさを表さない。','small'),
 p('文書・図・JSON：\nDocs/tests/cfd/\n2026-10-19_fixed_plate_refined/\n入力・生成・実行・検証スクリプト：\nanalysis/plate_cfd_20261019/\n元CAD断面・STL：\nanalysis/plate_cfd_20261018/geometry/','small'),
 p('入力、選択ケース、ログ、点時系列、主要全場、旧比較データを保持する。不採用格子と結果に使用しない中間平均場のみを整理し、削除一覧はresults/cleanup_manifest.jsonに記録する。中間平均場は同じ設定で再計算できるが、削除ファイルそのもののバックアップは作成しない。','small'),
 p('run_summary.json、mesh_quality.json、snapshot_comparison.json、geometry_provenance.jsonで値と出典を追跡できる。validation.jsonの成果物整合性合格は、数値解析の精度認定とは独立である。','small'),
 h('参考文献'),
],21,278,'p5')

refs=[
 ('[1] Gmsh, Reference Manual. 形状・格子生成。','https://gmsh.info/doc/texinfo/'),
 ('[2] NASA, Examining Iterative Convergence.','https://www.grc.nasa.gov/www/wind/valid/tutorial/iterconv.html'),
 ('[3] NASA, Examining Spatial (Grid) Convergence.','https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html'),
 ('[4] OpenCFD, fieldAverage, OpenFOAM 2606.','https://doc.openfoam.com/2606/tools/post-processing/function-objects/field/fieldAverage/'),
 ('[5] NIST, Wall and Blockage Effects in Air Speed Calibrations.','https://www.nist.gov/pml/sensor-science/fluid-metrology/wall-and-blockage-effects-air-speed-calibrations'),
 ('[6] OpenCFD, openfoam-run container images.','https://hub.docker.com/r/opencfd/openfoam-run/tags'),
]
refitems=[]
for label,url in refs:
    display=url.replace('https://','')
    refitems.append(Paragraph(escape(label)+'<br/><link href="'+url+'" color="#24556C">'+escape(display)+'</link>',STYLES['small']))
refitems.append(p('参照資料確認日：2026年10月19日。\n解析出典：WindTunnel Project内部保存データ（2026年10月18-19日）。','small'))
frame(refitems,M+CW+G,21,CW,172,'p5refs')
c.showPage()
c.save()
print(OUT)
