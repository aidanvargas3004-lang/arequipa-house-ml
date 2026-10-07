"""Catálogos y especificación de variables del modelo de tasación.

Los precios base por distrito (S/ por m² construido) son valores REFERENCIALES
aproximados, usados solo para generar el dataset sintético de demostración.
Deben ajustarse con datos reales de Arequipa House.
"""

# S/ por m² construido (aprox.) y nivel de zona (0 = económica … 3 = premium)
DISTRITOS = {
    "Yanahuara": {"pm2": 5900, "nivel": 3},
    "Cayma": {"pm2": 5000, "nivel": 3},
    "Arequipa (Cercado)": {"pm2": 5200, "nivel": 3},
    "José Luis Bustamante y Rivero": {"pm2": 4600, "nivel": 2},
    "Sachaca": {"pm2": 4300, "nivel": 2},
    "Miraflores": {"pm2": 3900, "nivel": 2},
    "Alto Selva Alegre": {"pm2": 3700, "nivel": 2},
    "Cerro Colorado": {"pm2": 3600, "nivel": 2},
    "Paucarpata": {"pm2": 3500, "nivel": 1},
    "Mariano Melgar": {"pm2": 3300, "nivel": 1},
    "Socabaya": {"pm2": 3200, "nivel": 1},
    "Sabandía": {"pm2": 3200, "nivel": 1},
    "Jacobo Hunter": {"pm2": 3100, "nivel": 1},
    "Tiabaya": {"pm2": 3000, "nivel": 1},
    "Characato": {"pm2": 2900, "nivel": 0},
    "Uchumayo": {"pm2": 2700, "nivel": 0},
    "Yura": {"pm2": 2300, "nivel": 0},
}
DISTRITO_NOMBRES = list(DISTRITOS.keys())

TIPOS = ["Casa", "Departamento", "Dúplex"]

# Orden creciente de calidad → índice numérico que usa el modelo
ESTADOS = ["Malo", "Regular", "Bueno", "Excelente"]
ACABADOS = ["Básico", "Estándar", "Alta calidad", "Lujo"]

# Columnas de entrada del modelo (en este orden)
CATEGORICAS = ["tipo", "distrito"]
NUMERICAS = [
    "area_terreno",
    "area_construida",
    "habitaciones",
    "banos",
    "pisos",
    "antiguedad",
    "estado_conservacion",
    "acabados",
    "cochera",
    "jardin",
    "piscina",
    "ascensor",
    "seguridad",
    "cerca_colegios",
    "cerca_hospitales",
    "cerca_comercial",
    "transporte_publico",
]
BOOLEANAS = [
    "jardin",
    "piscina",
    "ascensor",
    "seguridad",
    "cerca_colegios",
    "cerca_hospitales",
    "cerca_comercial",
    "transporte_publico",
]
FEATURE_COLUMNS = CATEGORICAS + NUMERICAS
TARGET = "precio"

# Etiquetas legibles para mostrar al usuario
ETIQUETAS = {
    "tipo": "Tipo de inmueble",
    "distrito": "Ubicación (distrito)",
    "area_terreno": "Área del terreno",
    "area_construida": "Área construida",
    "habitaciones": "Habitaciones",
    "banos": "Baños",
    "pisos": "Número de pisos",
    "antiguedad": "Antigüedad",
    "estado_conservacion": "Estado de conservación",
    "acabados": "Calidad de acabados",
    "cochera": "Cocheras",
    "jardin": "Jardín",
    "piscina": "Piscina",
    "ascensor": "Ascensor",
    "seguridad": "Seguridad / vigilancia",
    "cerca_colegios": "Cercanía a colegios",
    "cerca_hospitales": "Cercanía a hospitales",
    "cerca_comercial": "Cercanía a centros comerciales",
    "transporte_publico": "Acceso a transporte público",
}

# Límites de validación (compartidos por formularios y carga de CSV)
LIMITES = {
    "area_terreno": (10, 20000),
    "area_construida": (15, 3000),
    "habitaciones": (0, 15),
    "banos": (0, 12),
    "pisos": (1, 8),
    "antiguedad": (0, 100),
    "cochera": (0, 8),
    "precio": (20000, 20000000),
}

ORIGENES = ["sintetico", "csv", "manual", "venta"]
ORIGEN_ETIQUETA = {
    "sintetico": "Sintético (demostración)",
    "csv": "Archivo CSV",
    "manual": "Registro manual",
    "venta": "Venta cerrada en la plataforma",
}
