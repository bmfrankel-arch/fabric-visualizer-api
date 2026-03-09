"""
Build RH (Restoration Hardware) catalog JSON from browser-extracted data.

Data was extracted via Chrome browser automation from rh.com across 6 category pages:
- Sofas collections (14 items)
- Sectionals collections (13 items)
- Chairs products (28 unique)
- Swivel Chairs products (62 unique)
- Ottomans products (47 unique)
- Chaises products (26 unique)

Usage:
    python build_rh_catalog.py
"""

import json
import os
import re

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend', 'app')
OUTPUT_FILE = os.path.join(BACKEND_DIR, 'rh_catalog.json')

IMAGE_BASE = "https://media.restorationhardware.com/is/image/rhis/"
IMAGE_PARAMS = "?$PD$&illum=0"
RH_BASE = "https://rh.com/us/en/catalog/category"

# ── Sofa Collections (from collections.jsp?categoryId=cat25450027) ──
SOFAS = [
    ("The Original Cloud Sofa", "cat35200121", 4325, 7280),
    ("Cloud Track Arm Sofa", "cat35200123", 4719, 7940),
    ("Cloud Slope Arm Sofa", "cat35200125", 4719, 7940),
    ("Maxwell Sofa", "cat35200127", 3225, 5425),
    ("Maxwell Skirted Sofa", "cat35730008", 3225, 5425),
    ("Monastère Sofa", "cat35730004", 4585, 7710),
    ("Monastère Waterfall with Back Cushions Sofa", "cat35980003", 4415, 7425),
    ("Monastère Waterfall Sofa", "cat35730005", 4159, 6995),
    ("Modena Track Arm Sofa", "cat7150028-S23", 4629, 7795),
    ("Modena Track Arm Slipcovered Sofa", "cat35200132", 7379, 12445),
    ("Modena Slope Arm Sofa", "cat7150030", 4795, 8080),
    ("Modena Slope Arm Slipcovered Sofa", "cat35200134", 5059, 8525),
    ("Modena Taper Arm Sofa", "cat8780003-S23", 4629, 7795),
    ("Modena Taper Arm Slipcovered Sofa", "cat35200138", 5059, 8525),
]

# Sofa image IDs extracted from collections page
SOFA_IMAGES = {
    "cat35200121": "prod14890533_E21093052_TQ_RS_RHR",
    "cat35200123": "prod15590025_E59684440_TQ_CC_RHR",
    "cat35200125": "prod15590013_E39684212_TQ_CC_RHR",
    "cat35200127": "prod1871202_E114390093_TQ_Frank_RHR",
    "cat35730008": "prod38800549_E814405186_TQ_Frank_CC_RHR",
    "cat35730004": "prod38810574_E25524826820_TQ_Frank_RHR",
    "cat35980003": "prod38810558_E2552482704_TQ_Frank_RHR",
    "cat35730005": "prod38810542_E25524827140_TQ_Frank_RHR",
    "cat7150028-S23": "prod7550177_E87802076_TQ_CC_RHR",
    "cat35200132": "prod35950063_E24824222746_TQ_CC_RHR",
    "cat7150030": "prod7560033_E67804305_TQ_CC_RHR",
    "cat35200134": "prod35950067_E24824222914_TQ_CC_RHR",
    "cat8780003-S23": "prod8780022_E47913792_TQ_CC_RHR",
    "cat35200138": "prod35950071_E25024223062_TQ_CC_RHR",
}

# ── Sectional Collections (from collections.jsp?categoryId=cat10210006) ──
SECTIONALS = [
    ("The Original Cloud Sectional", "cat6120041", 6008, 10140),
    ("Cloud Track Arm Sectional", "cat34700004", 7298, 12290),
    ("Cloud Modular Track Arm Sectional", "cat14150064", 7298, 12290),
    ("Cloud Slope Arm Sectional", "cat34700003", 7298, 12290),
    ("Cloud Slope Arm Modular Sectional", "cat14150060", 7298, 12290),
    ("Maxwell Sectional", "cat25210016", 5618, 9460),
    ("Maxwell Skirted Sectional", "cat35610007", 5774, 9720),
    ("Monastère Sectional", "cat35430009", 7604, 12800),
    ("Monastère Waterfall Sectional", "cat35430010", 7210, 12140),
    ("Modena Track Arm Sectional", "cat10560008", 6888, 11600),
    ("Modena Slope Arm Sectional", "cat10560009", 6888, 11600),
    ("Modena Taper Arm Sectional", "cat10560010", 6888, 11600),
    ("Modena Slipcovered Sectional", "cat35200140", 9518, 16040),
]

SECTIONAL_IMAGES = {
    "cat6120041": "prod14890533_E21093052_TQ_RS_RHR",
    "cat34700004": "prod15590025_E59684440_TQ_CC_RHR",
    "cat14150064": "prod15590025_E59684440_TQ_CC_RHR",
    "cat34700003": "prod15590013_E39684212_TQ_CC_RHR",
    "cat14150060": "prod15590013_E39684212_TQ_CC_RHR",
    "cat25210016": "prod1871202_E114390093_TQ_Frank_RHR",
    "cat35610007": "prod38800549_E814405186_TQ_Frank_CC_RHR",
    "cat35430009": "prod38810574_E25524826820_TQ_Frank_RHR",
    "cat35430010": "prod38810542_E25524827140_TQ_Frank_RHR",
    "cat10560008": "prod7550177_E87802076_TQ_CC_RHR",
    "cat10560009": "prod7560033_E67804305_TQ_CC_RHR",
    "cat10560010": "prod8780022_E47913792_TQ_CC_RHR",
    "cat35200140": "prod35950063_E24824222746_TQ_CC_RHR",
}

# ── Products page items (163 unique, extracted from browser) ──
# Format: name|imageId|memberPrice|regularPrice|type
PRODUCTS_DATA = """1950s Italian Shelter Arm Swivel Chair|prod20580100_E414854120_TQ_CC_RHR|1349|2280|Swivel Chair
Arrondi Swivel Chair|prod34270116_E24222944635_TQ_CC_RHR|1329|2240|Swivel Chair
Oliver Track Arm Swivel Chair|prod35040017_E24923473610_TQ_RHR|1419|2395|Swivel Chair
Oliver Slope Arm Swivel Chair|prod35040013_E24223473285_TQ_CC_RHR|1419|2395|Swivel Chair
Oliver Barrelback Track Arm Swivel Chair|prod35651012_E313208826_TQ_Frank_RHR|1675|2395|Swivel Chair
Oliver Barrelback Slope Arm Swivel Chair|prod36620018_E24623473028_TQ_CC_RHR|1675|2395|Swivel Chair
Oliver Slipcovered Track Arm Swivel Chair|prod37310062_E25224376437_TQ_CC_RHR|1995|2850|Swivel Chair
Oliver Slipcovered Slope Arm Swivel Chair|prod37310067_E25324376119_TQ_RHR|1995|2850|Swivel Chair
Oliver Slipcovered Barrelback Track Arm Swivel Chair|prod37310065_E25324376793_TQ_RHR|2075|2965|Swivel Chair
Oliver Slipcovered Barrelback Slope Arm Swivel Chair|prod37310069_E25724376311_TQ_CC_RHR|1689|2850|Swivel Chair
Library Swivel Chair|prod37830014_E25224477623_TQ_Frank_RHR|2395|3425|Swivel Chair
Library Swivel Chair with Nailheads|prod38300008_E25224477623_TQ_Frank_RHR|2495|3565|Swivel Chair
Evelyn Skirted Slope Arm Swivel Chair|prod37290112_E2524378626_TQ_RHR|2195|3140|Swivel Chair
Evelyn Skirted Shelter Arm Swivel Chair|prod37290111_E25824378883_TQ_CC_RHR|1865|3140|Swivel Chair
Luisa Swivel Chair|prod34960012_E24323406855_TQ_CC_RHR|1015|1710|Swivel Chair
Adriana Swivel Chair|prod34600259_E242331095_TQ_CC_RHR|1015|1710|Swivel Chair
Caite Swivel Chair|prod34960018_E2422340761_TQ_RHR|1015|1710|Swivel Chair
Sofia Swivel Chair|prod30900283_E23821280090_TQ_CC_RHR|1505|2540|Swivel Chair
Reyna Swivel Chair|prod28470273_E22519716186_TQ_CC_RHR|1525|2565|Swivel Chair
Sora Swivel Chair|prod35810738_E24723911022_TQ_CC_RHR|1095|1565|Swivel Chair
Aria Swivel Chair|prod28470214_E22919731841_TQ_RHR|1995|2850|Swivel Chair
Botero Swivel Chair|prod35810732_E24823910112_TQ_CC_RHR|1795|2565|Swivel Chair
Copenhagen Swivel Chair|prod25150389_E21818314858_TQ_CC_RHR|2735|3910|Swivel Chair
Emilia Swivel Chair|prod30620238_E23621109713_TQ_CC_RHR|1300|1860|Swivel Chair
Lara Swivel Chair|prod31870243_E23821695574_TQ_RHR|1505|2150|Swivel Chair
Boson Swivel Chair|prod30640478_E23721128559_TQ_RHR|2609|4975|Swivel Chair
Luke Swivel Chair|prod15140022_E37880168_TQ_XBC_ReBG_RHR|3390|4845|Swivel Chair
Luke Swivel Recliner|prod14920059_E410809456_TQ_XBC_ReBG_RHR|3890|5560|Swivel Chair
Gianna Swivel Chair|prod34600157_E24523308794_TQ_RHR|2295|3280|Swivel Chair
Gianna Recliner|prod34950147_E24423397574_TQ_RHR|3310|4730|Swivel Chair
Dixon Upholstered Swivel Chair|prod38800722_E26924960022_TQ_RHR|1795|2565|Swivel Chair
Dixon Swivel Chair|prod13160116_E61273863_TQ_CC_RHR|2395|3425|Swivel Chair
Reginald Swivel Chair|prod34400005_E242287532_TQ_RHR|2395|3425|Swivel Chair
Lucio Swivel Chair|prod32200296_E23321912035_TQ_CC_RHR|2285|3850|Swivel Chair
Lario Swivel Chair|prod32200294_E23221911893_TQ_CC_RHR|1609|2710|Swivel Chair
Lanzo Swivel Chair|prod32200298_E23421912260_TQ_RHR|2119|3565|Swivel Chair
Gustavo Swivel Chair|prod36920021_E25423976660_TQ_CC_RHR|1195|1710|Swivel Chair
Drew Swivel Chair|prod10370015_E27625395_TQ_XBC_ReBG_RHR|2695|3850|Swivel Chair
Drew Curved Swivel Chair|prod18940583_E313222298_TQ_RHR|2695|3850|Swivel Chair
Arden Swivel Chair|prod19230226_E113219598_TQ_XBC_ReBG_RHR|1995|2850|Swivel Chair
Gia Open-Back Swivel Chair|prod31750072_E23821576470_TQ_RHR|1235|1765|Swivel Chair
Gia Swivel Chair|prod31750068_E23521576044_TQ_CC_RHR|1235|1765|Swivel Chair
Taite Swivel Chair|prod25150334_E717694452_TQ_RHR|3355|5565|Swivel Chair
Austen Swivel Chair - Metal Base|prod28470255_E22219735672_TQ_Frank_RHR|1795|2565|Swivel Chair
Austen Swivel Chair - Oak Base|prod28470253_E22219735672_TQ_CC_RHR|1795|2565|Swivel Chair
Mira Swivel Chair|prod32530014_TQ_Frank_RHR|2995|4280|Swivel Chair
Napoli Swivel Chair|prod28470245_E22219734863_TQ_RS_RHR|1885|3140|Swivel Chair
Savio Swivel Chair|prod28470243_E22319734643_TQ_RS1_RHR|2235|3710|Swivel Chair
Lecco Swivel Chair|prod27210510_E22519282534_TQ_CC_RHR|2595|3710|Swivel Chair
Churchill Swivel Chair|prod2180006_RHR|2529|4260|Swivel Chair
Churchill Swivel Chair with Nailheads|prod1871212_E61568060_TQ_RHR|2529|4260|Swivel Chair
Adriano Swivel Chair|prod28470247_E22119735087_TQ_RS_RHR|2295|3280|Swivel Chair
Maxwell Swivel Chair|prod1871214_E114390093_TQ_Frank_RHR|3395|4850|Swivel Chair
Maxwell Skirted Swivel Chair|prod38800553_E814405186_TQ_Frank_CC_RHR|3695|5280|Swivel Chair
Monastère Swivel Chair|prod38810578_E25524827246_TQ_Frank_RHR|4095|5850|Swivel Chair
Monastère Waterfall with Back Cushion Swivel Chair|prod38810562_E25224827382_TQ_Frank_RHR|3895|5565|Swivel Chair
Monastère Waterfall Swivel Chair|prod38810546_E2524827421_TQ_Frank_RHR|3695|5280|Swivel Chair
Belgian Track Arm Swivel Chair|prod2140643_RHR|2119|3565|Swivel Chair
Belgian Classic Slope Arm Swivel Chair|prod2430104_E84355338_TQ_Frank_RHR|2119|3565|Swivel Chair
Belgian Slope Arm Swivel Chair|prod1871208_E64360370_TQ_Frank_RHR|2119|3565|Swivel Chair
Belgian Slipcovered Track Arm Swivel Chair|prod80398_TQ_RHR|2375|3995|Swivel Chair
Belgian Slipcovered Classic Slope Arm Swivel Chair|prod2420408_RHR|2375|3995|Swivel Chair
Cooper Square Stool|prod2290002_E25724573529_F_RHR|655|940|Ottoman
Cooper Rectangular Stool|prod2110096_E25224573366_F_RHR|780|1120|Ottoman
Small Cooper Round Stool|prod38380051_E25124568567_F_RHR|655|940|Ottoman
Large Cooper Round Stool|prod38380050_E25424568429_F_RHR|990|1420|Ottoman
Rex Rectangular Stool - Metal Base|prod7490123_E27625090_F_RHR|655|940|Ottoman
Rex Rectangular Stool - Oak Base|prod20970312_E415420330_F_Frank_CC_RHR|655|940|Ottoman
Rex Channel-Tufted Round Stool - Oak Base|prod21110007_E315436986_F_RHR|640|915|Ottoman
Rex Round Stool - Oak Base|prod21110020_E515436775_F_XBC_ReBG_RHR|655|940|Ottoman
Rex Channel-Tufted Round Stool - Metal Base|prod20530039_E81542089_F_RHR|640|915|Ottoman
Maxwell Ottoman|prod20240026_E14390311_F_Frank_RHR|755|1280|Ottoman
Cloud Ottoman|prod14890576_E21093225_F_RHR|1275|1825|Ottoman
Belgian Collection Ottoman|prod2430308_av1_RHR|589|995|Ottoman
Belgian Slipcovered Collection Ottoman|prod2420414_av1_RHR|639|1080|Ottoman
English Classic Roll Arm Ottoman|prod1861147_E65396096_F_RHR|1205|1725|Ottoman
English Slipcovered Classic Roll Arm Ottoman|prod60119_av1_RHR|1315|1880|Ottoman
Modena Ottoman|prod8120386_E47896474_TQ_CC_RHR|1329|2250|Ottoman
Arno Ottoman|prod38060193_E25924506138_F_RHR|595|850|Ottoman
Arno Vegan Leather Ottoman|prod38060192_E25324506256_F_RHR|595|850|Ottoman
Italia Ottoman - Metal Base|prod7500932_E67622870_F_Frank_RHR|1329|2240|Ottoman
Italia Ottoman - Oak Base|prod16920161_E110956064_F_XBC_ReBG_RHR|1335|2250|Ottoman
Italia Chesterfield Ottoman with Tufted Cushion - Metal Base|prod14970241_E712463223_F_RHR|1329|2240|Ottoman
Cortona Small Cushion Back Wide-Arm Ottoman|prod27090100_E2161831402_F_CC_RHR|2775|3965|Ottoman
Parisian Ottoman|prod13070005_E514021911_F_RS_RHR|1095|1565|Ottoman
Maddox Ottoman|prod16640048_E711587484_F_XBC_ReBG_RHR|1215|1740|Ottoman
Maddox Slim-Arm Ottoman|prod18220177_E812751398_F_RHR|1215|1740|Ottoman
Oliver Ottoman|prod17390020_E611861724_F_RHR|780|1120|Ottoman
Thaddeus Ottoman|prod24540167_E317104174_F_CC_RHR|2085|2985|Ottoman
Celine Ottoman|prod23810065_E518215331_F_RHR|1405|2365|Ottoman
Monza Ottoman|prod18910070_E713207164_F_RHR|2185|3680|Ottoman
Original Lancaster Ottoman|prod1633053_E24363950_TQ_CC_RHR|775|1310|Ottoman
Churchill Ottoman with Nailheads|prod1870703_av1_RHR|945|1595|Ottoman
Churchill Ottoman|prod2180019_av1_RHR|865|1460|Ottoman
1920s Parisian Club Ottoman|prod2702023_E94207387_F_RHR|1465|2425|Ottoman
Vittorio Ottoman|prod28210090_E22319645333_F_RHR|1405|2365|Ottoman
Sorensen Ottoman|prod2110640_av1_RHR|989|1665|Ottoman
Bridge Fabric Rectangular Coffee Table Ottoman|prod37180089_E410235349_F_CC_RHR|2725|3895|Ottoman
Cloud Coffee Ottoman|prod6490276_E97032323_F_RS_RHR|1695|2425|Ottoman
Maxwell Coffee Ottoman|prod2110779_E114392636_F_RHR|1495|2140|Ottoman
Modena Coffee Ottoman|prod7610522_E27896547_F_RHR|1605|2710|Ottoman
French Contemporary Fabric Rectangular Coffee Ottoman|prod20810194_E211742652_F_CC_RHR|1445|2410|Ottoman
French Contemporary Fabric Square Coffee Ottoman|prod20810195_E211742652_F_CC_RHR|2045|3415|Ottoman
Italia Coffee Ottoman - Metal Base|prod7500926_E67622870_F_RHR|1925|3240|Ottoman
Italia Coffee Ottoman - Oak Base|prod16920150_E110956064_F_XBC_ReBG_RHR|1685|2840|Ottoman
Italia Chesterfield Coffee Ottoman with Tufted Cushion - Metal Base|prod7510198_E97795640_F_RHR|1925|3240|Ottoman
Thaddeus Fabric Rectangular Coffee Ottoman|prod17640026_E210723531_F_Frank_RHR|4215|7025|Ottoman
Thaddeus Fabric Square Coffee Ottoman|prod17900008_E210723531_F_Frank_RHR|6015|10025|Ottoman
Original Lancaster Coffee Ottoman|prod2110868_E14364028_F_CC_RHR|1999|3365|Ottoman
1950s Italian Shelter Arm Chair|prod15950247_E23321716473_TQ_CC_RHR|1155|1945|Chair
Arrondi Chair|prod34310070_E24322864558_TQ_CC_RHR|1460|2090|Chair
Evelyn Skirted Slope Arm Chair|prod37290112_E2524378626_TQ_CC_RHR|2095|2995|Chair
Jude Chair|prod38280010_E2552452664_TQ_RHR|1195|1710|Chair
Library Chair with Nailheads|prod38300009_E25224477623_TQ_Frank_RHR|2395|3425|Chair
Reyna Chair|prod27940139_E22719687892_TQ_CC_RHR|1610|2305|Chair
Aria Chair|prod28470214_E22919731841_TQ_RHR|1895|2710|Chair
Copenhagen Chair|prod25910048_E22218986430_TQ_RHR|2535|3625|Chair
Noa Chair|prod35810745_E24523911737_TQ_RS_RHR|1395|2280|Chair
Jakob Lounge Chair|prod33840091_E23221121288_TQ_V1_CC_RHR|795|1345|Chair
Jakob Vegan Leather Lounge Chair|prod36340022_E25424120261_TQ_CC_RHR|995|1425|Chair
Jakob Armless Lounge Chair|prod39201570_E25824826112_TQ_RHR|895|1280|Chair
Jakob Vegan Leather Armless Lounge Chair|prod38800706_E2582482641_TQ_RHR|1095|1565|Chair
Arno Luxe Lounge Chair|prod39010433_E26724940348_TQ_RHR|1195|1710|Chair
Arno Lounge Chair|prod35360148_E25124474787_TQ_RHR|995|1425|Chair
Arno Vegan Leather Lounge Chair|prod33670064_E24222730227_TQ_RS_RHR|845|1425|Chair
Frontier Chair|prod35560009_E24223638884_TQ_CC_RHR|1675|2710|Chair
Fino Chair|prod35810735_E24223910790_TQ_RHR|1595|2280|Chair
Owen Chair|prod34600153_E24523308387_TQ_RHR|1865|3140|Chair
Thaddeus Track Arm Chair|prod24540157_E617103925_TQ_CC_RHR|4995|7140|Chair
Thaddeus Slope Arm Chair|prod24540155_E41710370_TQ_CC_RHR|4955|7085|Chair
Thaddeus Armless Chair|prod24540165_E1710360_TQ_CC_RHR|3985|5695|Chair
Thaddeus Barrelback Slope Arm Chair|prod21850018_E215631522_TQ_CC_RHR|3445|4925|Chair
Thaddeus X-Base Slipper Chair|prod24540159_E617104253_TQ_CC_RHR|5195|7425|Chair
Thaddeus Curved Chair|prod24940187_E115572614_TQ_CC_RHR|4595|6565|Chair
Dixon Upholstered Chair|prod38800720_E26924960022_TQ_Frank_RHR|1695|2425|Chair
Gia Open-Back Chair|prod31750070_E23621576273_TQ_RHR|1130|1615|Chair
Gia Chair|prod31750066_E2392157580_TQ_CC_RHR|1130|1615|Chair
Oviedo Chaise|prod21270163_E416270831_TQ_CC_RHR|2515|4140|Chaise
René Chaise|prod20420080_E914213574_TQ_CC_RHR|3995|5710|Chaise
Rossi Chaise|prod19910022_E97626149_TQ_XBC_ReBG_RHR|3095|4425|Chaise
Royce Chaise|prod19910026_E17630995_TQ_CC_RHR|2465|3525|Chaise
Cloud Chaise|prod6490272_E96746746_TQ_RHR|4960|7090|Chaise
Maxwell Chaise|prod80148_E11439016_TQ_RHR|4595|6565|Chaise
Modena Track Arm Chaise|prod7551891_E87802431_TQ_RHR|4279|7210|Chaise
Modena Slope Arm Chaise|prod7560041_E57804515_TQ_RHR|4279|7210|Chaise
Sorensen Chaise|prod6512555_E8684810_TQ_RHR|2539|4280|Chaise
Nadine Daybed|prod38900014_E25624830942_F_RHR|2395|3425|Chaise
Nadine Upholstered Daybed|prod38900013_E25424830879_F_RHR|1995|2850|Chaise
Byron Fabric Daybed|prod34451710_E2524014222_F_RHR|3539|5950|Chaise
Ligné Fabric Panel Daybed|prod32320068_E23421106841_F_CC_RHR|2835|4765|Chaise
Gael Oak Fabric Panel Daybed|prod35410166_E2442364260_F_CC_RHR|2119|4240|Chaise
Ciro Fabric Double-Arm Daybed|prod32350162_E23321109047_F_CC_RHR|6465|9240|Chaise
Ciro Fabric Left-Arm Daybed|prod32350156_E23721321388_F_Frank_Flip_RHR|6150|8790|Chaise
Ciro Fabric Right-Arm Daybed|prod32350159_E23721321388_F_CC_RHR|6150|8790|Chaise
Padua Fabric Double-Bolster Daybed|prod32320288_E23321492871_F_CC_RHR|2389|4775|Chaise
Bode Fabric Daybed|prod32030193_E2321743273_F_RHR|3470|4960|Chaise
Josephine Fabric Double-Bolster Daybed|prod32030187_E23621141557_F_Frank_CC_RHR|5009|13025|Chaise
Byron Reeded Stone Fabric Daybed|prod31710302_E2321560354_F_RHR|10595|15140|Chaise
Gael Walnut Fabric Daybed|prod30610180_E23821108385_F_RHR|2915|6955|Chaise
Cortona Small Cushion Back Wide-Arm Daybed|prod27510230_E22819051663_TQ_CC_RHR|12855|18365|Chaise
Cortona Small Cushion Back Daybed|prod27010009_E2281905166_TQ_Frank_RHR|13055|18650|Chaise
Cloud Daybed|prod6490271_E66746956_F_RS_RHR|7290|10415|Chaise
Costera Modular 2-piece Daybed|prod17480030_E911910063_F_RHR|9649|16225|Chaise"""


def extract_collection(name: str) -> str:
    """Extract collection name from product name."""
    # Remove common suffixes
    cleaned = name
    for suffix in ['Sofa', 'Sectional', 'Swivel Chair', 'Chair', 'Ottoman',
                   'Chaise', 'Daybed', 'Stool', 'Recliner',
                   'with Nailheads', 'with Tufted Cushion',
                   'with Back Cushions', 'with Back Cushion',
                   '- Metal Base', '- Oak Base',
                   'Slipcovered', 'Skirted', 'Modular 2-piece',
                   'Coffee Table', 'Coffee', 'Rectangular', 'Square',
                   'Double-Arm', 'Left-Arm', 'Right-Arm', 'Double-Bolster',
                   'Reeded Stone', 'Vegan Leather', 'Upholstered',
                   'Wide-Arm', 'Slim-Arm', 'Armless', 'Open-Back',
                   'Barrelback', 'Curved', 'X-Base Slipper',
                   'Track Arm', 'Slope Arm', 'Taper Arm', 'Shelter Arm',
                   'Roll Arm', 'Classic', 'Small Cushion Back',
                   'Channel-Tufted', 'Fabric', 'Panel', 'Luxe',
                   'Lounge', 'Round', 'Large', 'Small']:
        cleaned = cleaned.replace(suffix, '')

    # Clean up whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' -,')

    if len(cleaned) < 2:
        # Fall back to first word(s)
        parts = name.split()
        cleaned = parts[0] if parts else name

    return cleaned


def build_catalog():
    catalog = []
    seen_names = set()

    # ── Add Sofas ──
    for name, cat_id, member_price, regular_price in SOFAS:
        image_id = SOFA_IMAGES.get(cat_id, '')
        if not image_id:
            continue
        catalog.append({
            'name': name,
            'sku': cat_id,
            'price': member_price,
            'compare_at_price': regular_price,
            'on_sale': True,
            'collection': extract_collection(name),
            'color': 'Varies',
            'url': f'{RH_BASE}/collections.jsp/{cat_id}',
            'image_url': f'{IMAGE_BASE}{image_id}{IMAGE_PARAMS}',
            'category': 'Living',
            'type': 'Sofa',
            'brand': 'RH',
            'material': 'Fabric',
        })
        seen_names.add(name)

    # ── Add Sectionals ──
    for name, cat_id, member_price, regular_price in SECTIONALS:
        image_id = SECTIONAL_IMAGES.get(cat_id, '')
        if not image_id:
            continue
        catalog.append({
            'name': name,
            'sku': cat_id,
            'price': member_price,
            'compare_at_price': regular_price,
            'on_sale': True,
            'collection': extract_collection(name),
            'color': 'Varies',
            'url': f'{RH_BASE}/collections.jsp/{cat_id}',
            'image_url': f'{IMAGE_BASE}{image_id}{IMAGE_PARAMS}',
            'category': 'Living',
            'type': 'Sectional',
            'brand': 'RH',
            'material': 'Fabric',
        })
        seen_names.add(name)

    # ── Add Products page items ──
    for line in PRODUCTS_DATA.strip().split('\n'):
        parts = line.split('|')
        if len(parts) != 5:
            continue
        name, image_id, price_str, regular_str, ptype = parts
        name = name.strip()
        if name in seen_names:
            continue
        seen_names.add(name)

        price = int(price_str)
        regular = int(regular_str)
        on_sale = regular > price

        catalog.append({
            'name': name,
            'sku': image_id.split('_')[0] if '_' in image_id else image_id,
            'price': price,
            'compare_at_price': regular,
            'on_sale': on_sale,
            'collection': extract_collection(name),
            'color': 'Varies',
            'url': 'https://rh.com',
            'image_url': f'{IMAGE_BASE}{image_id}{IMAGE_PARAMS}',
            'category': 'Living',
            'type': ptype,
            'brand': 'RH',
            'material': 'Fabric',
        })

    # Sort by type, then name
    type_order = ['Sectional', 'Sofa', 'Chaise', 'Swivel Chair', 'Chair', 'Ottoman']
    catalog.sort(key=lambda p: (
        type_order.index(p['type']) if p['type'] in type_order else 99,
        p['name']
    ))

    return catalog


def main():
    print("=" * 70)
    print("RH (Restoration Hardware) Catalog Builder")
    print("=" * 70)
    print()

    catalog = build_catalog()

    # Summary by type
    type_counts = {}
    for p in catalog:
        t = p['type']
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"Total products: {len(catalog)}")
    print()
    print("By type:")
    for t in ['Sectional', 'Sofa', 'Chaise', 'Swivel Chair', 'Chair', 'Ottoman']:
        if t in type_counts:
            print(f"  {t:20s} {type_counts[t]:4d}")

    # Price range
    prices = [p['price'] for p in catalog if p['price'] > 0]
    if prices:
        print(f"\nPrice range: ${min(prices):,.0f} - ${max(prices):,.0f}")

    # Collections
    collections = set(p['collection'] for p in catalog)
    print(f"Unique collections: {len(collections)}")

    # Write output
    print(f"\nWriting {len(catalog)} products to {OUTPUT_FILE}")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print(f"Output saved to: {OUTPUT_FILE}")
    print("Done!")


if __name__ == '__main__':
    main()
