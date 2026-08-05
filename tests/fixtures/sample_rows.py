"""Representatieve queryresultaten voor gebruik in tests."""

LADEN_RIJEN = [
    (
        "2026-06-08",
        "Laden",
        "Burgerboerderij de Patrijs",
        "Dochterenseweg",
        "7245 NN",
        "Laren",
        6,
        1,
        "1236833",
        "4 tot 7",
        19.85,
    ),
    (
        "2026-06-10",
        "Laden",
        "De Goed Gevulde Boerderij",
        "Halsedijk 8",
        "4273 NA",
        "Halle",
        7,
        4,
        "1239005, 1239006, 1239007, 1239008",
        "7 tot 10",
        23.55,
    ),
    (
        "2026-06-10",
        "Laden",
        "Burgerboerderij de Patrijs",
        "Dochterenseweg",
        "7245 NN",
        "Laren",
        5,
        3,
        "1239013, 1239014, 1239015",
        "4 tot 7",
        19.85,
    ),
]

LOSSEN_RIJEN = [
    (
        "2026-06-10",
        "Lossen",
        "Depot Miedema",
        "Industrieweg 1",
        "7245 AA",
        "Laren",
        12,
        1,
        "1239005",
        "10 tot 15",
        31.50,
    ),
]

GEMENGDE_RIJEN = LADEN_RIJEN + LOSSEN_RIJEN

# Spoed-rijen: 8 velden (datum, order_id, van_naam, van_adres, naar_naam, naar_adres, colli, tarief)
SPOED_RIJEN = [
    (
        "2026-06-10",
        "1245429",
        "Groothandel BD Totaal",
        "Lichtschip 31, 3991CP Houten",
        "Gemeenschapsboerderij Erve Kiekebos",
        "Breestraat 9, 7399RE Empe",
        50,
        200.0,
    ),
]
