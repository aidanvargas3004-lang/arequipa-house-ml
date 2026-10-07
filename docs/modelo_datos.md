# Modelo de datos

## Diagrama entidad-relación

```mermaid
erDiagram
    usuarios ||--o{ modelos_ml : "creado_por_id"
    usuarios ||--o{ propiedades : "vendedor_id"
    usuarios ||--o{ favoritos : "usuario_id"
    propiedades ||--o{ favoritos : "propiedad_id"
    propiedades ||--o{ fotos : "propiedad_id"
    propiedades ||--o{ mensajes : "propiedad_id"
    usuarios ||--o{ mensajes : "comprador_id"
    usuarios ||--o{ mensajes : "autor_id"
    usuarios ||--o{ tasaciones : "usuario_id"
    modelos_ml ||--o{ tasaciones : "modelo_id"
    propiedades ||--o{ tasaciones : "propiedad_id"
    propiedades ||--o{ visitas : "propiedad_id"
    usuarios ||--o{ visitas : "comprador_id"
    ajustes_distrito {
        VARCHAR distrito PK
        FLOAT factor
    }
    dataset_registros {
        INTEGER id PK
        VARCHAR tipo
        VARCHAR distrito
        FLOAT area_terreno
        FLOAT area_construida
        INTEGER habitaciones
        INTEGER banos
        INTEGER pisos
        INTEGER antiguedad
        VARCHAR estado_conservacion
        VARCHAR acabados
        INTEGER cochera
        INTEGER jardin
        INTEGER piscina
        INTEGER ascensor
        INTEGER seguridad
        INTEGER cerca_colegios
        INTEGER cerca_hospitales
        INTEGER cerca_comercial
        INTEGER transporte_publico
        FLOAT precio
        VARCHAR origen
        DATETIME creado_en
    }
    parametros {
        VARCHAR clave PK
        VARCHAR valor
        VARCHAR descripcion
    }
    usuarios {
        INTEGER id PK
        VARCHAR nombre
        VARCHAR email
        VARCHAR telefono
        VARCHAR password_hash
        VARCHAR rol
        BOOLEAN activo
        INTEGER intentos_fallidos
        DATETIME bloqueado_hasta
        DATETIME creado_en
        DATETIME ultimo_acceso
    }
    modelos_ml {
        INTEGER id PK
        INTEGER version
        VARCHAR algoritmo
        VARCHAR archivo
        VARCHAR estado
        BOOLEAN activo
        JSON metricas
        JSON composicion
        VARCHAR error
        INTEGER creado_por_id FK
        DATETIME creado_en
        DATETIME terminado_en
    }
    propiedades {
        INTEGER id PK
        INTEGER vendedor_id FK
        VARCHAR titulo
        TEXT descripcion
        VARCHAR direccion
        VARCHAR tipo
        VARCHAR distrito
        FLOAT area_terreno
        FLOAT area_construida
        INTEGER habitaciones
        INTEGER banos
        INTEGER pisos
        INTEGER antiguedad
        VARCHAR estado_conservacion
        VARCHAR acabados
        INTEGER cochera
        BOOLEAN jardin
        BOOLEAN piscina
        BOOLEAN ascensor
        BOOLEAN seguridad
        BOOLEAN cerca_colegios
        BOOLEAN cerca_hospitales
        BOOLEAN cerca_comercial
        BOOLEAN transporte_publico
        FLOAT precio
        VARCHAR estado
        VARCHAR motivo_rechazo
        DATETIME creado_en
        DATETIME actualizado_en
    }
    favoritos {
        INTEGER id PK
        INTEGER usuario_id FK
        INTEGER propiedad_id FK
        DATETIME creado_en
    }
    fotos {
        INTEGER id PK
        INTEGER propiedad_id FK
        VARCHAR archivo
        INTEGER orden
    }
    mensajes {
        INTEGER id PK
        INTEGER propiedad_id FK
        INTEGER comprador_id FK
        INTEGER autor_id FK
        TEXT contenido
        BOOLEAN leido
        DATETIME creado_en
    }
    tasaciones {
        INTEGER id PK
        INTEGER usuario_id FK
        INTEGER modelo_id FK
        INTEGER propiedad_id FK
        JSON datos
        FLOAT precio_estimado
        FLOAT precio_min
        FLOAT precio_max
        FLOAT precio_m2
        JSON factores
        DATETIME creado_en
    }
    visitas {
        INTEGER id PK
        INTEGER propiedad_id FK
        INTEGER comprador_id FK
        DATETIME fecha_hora
        VARCHAR modalidad
        VARCHAR comentario
        VARCHAR estado
        VARCHAR respuesta
        DATETIME creado_en
    }
```

## Diccionario de datos

| Tabla | Campo | Tipo | Nulo | Clave |
|---|---|---|---|---|
| ajustes_distrito | distrito | VARCHAR(60) | no | PK |
| ajustes_distrito | factor | FLOAT | no |  |
| dataset_registros | id | INTEGER | no | PK |
| dataset_registros | tipo | VARCHAR(20) | no |  |
| dataset_registros | distrito | VARCHAR(60) | no |  |
| dataset_registros | area_terreno | FLOAT | no |  |
| dataset_registros | area_construida | FLOAT | no |  |
| dataset_registros | habitaciones | INTEGER | no |  |
| dataset_registros | banos | INTEGER | no |  |
| dataset_registros | pisos | INTEGER | no |  |
| dataset_registros | antiguedad | INTEGER | no |  |
| dataset_registros | estado_conservacion | VARCHAR(20) | no |  |
| dataset_registros | acabados | VARCHAR(20) | no |  |
| dataset_registros | cochera | INTEGER | no |  |
| dataset_registros | jardin | INTEGER | no |  |
| dataset_registros | piscina | INTEGER | no |  |
| dataset_registros | ascensor | INTEGER | no |  |
| dataset_registros | seguridad | INTEGER | no |  |
| dataset_registros | cerca_colegios | INTEGER | no |  |
| dataset_registros | cerca_hospitales | INTEGER | no |  |
| dataset_registros | cerca_comercial | INTEGER | no |  |
| dataset_registros | transporte_publico | INTEGER | no |  |
| dataset_registros | precio | FLOAT | no |  |
| dataset_registros | origen | VARCHAR(15) | no |  |
| dataset_registros | creado_en | DATETIME | no |  |
| parametros | clave | VARCHAR(60) | no | PK |
| parametros | valor | VARCHAR(60) | no |  |
| parametros | descripcion | VARCHAR(200) | no |  |
| usuarios | id | INTEGER | no | PK |
| usuarios | nombre | VARCHAR(120) | no |  |
| usuarios | email | VARCHAR(160) | no |  |
| usuarios | telefono | VARCHAR(30) | sí |  |
| usuarios | password_hash | VARCHAR(255) | no |  |
| usuarios | rol | VARCHAR(20) | no |  |
| usuarios | activo | BOOLEAN | no |  |
| usuarios | intentos_fallidos | INTEGER | no |  |
| usuarios | bloqueado_hasta | DATETIME | sí |  |
| usuarios | creado_en | DATETIME | no |  |
| usuarios | ultimo_acceso | DATETIME | sí |  |
| modelos_ml | id | INTEGER | no | PK |
| modelos_ml | version | INTEGER | no |  |
| modelos_ml | algoritmo | VARCHAR(30) | sí |  |
| modelos_ml | archivo | VARCHAR(120) | sí |  |
| modelos_ml | estado | VARCHAR(12) | no |  |
| modelos_ml | activo | BOOLEAN | no |  |
| modelos_ml | metricas | JSON | sí |  |
| modelos_ml | composicion | JSON | sí |  |
| modelos_ml | error | VARCHAR(400) | sí |  |
| modelos_ml | creado_por_id | INTEGER | sí | FK → usuarios.id |
| modelos_ml | creado_en | DATETIME | no |  |
| modelos_ml | terminado_en | DATETIME | sí |  |
| propiedades | id | INTEGER | no | PK |
| propiedades | vendedor_id | INTEGER | no | FK → usuarios.id |
| propiedades | titulo | VARCHAR(160) | no |  |
| propiedades | descripcion | TEXT | no |  |
| propiedades | direccion | VARCHAR(200) | no |  |
| propiedades | tipo | VARCHAR(20) | no |  |
| propiedades | distrito | VARCHAR(60) | no |  |
| propiedades | area_terreno | FLOAT | no |  |
| propiedades | area_construida | FLOAT | no |  |
| propiedades | habitaciones | INTEGER | no |  |
| propiedades | banos | INTEGER | no |  |
| propiedades | pisos | INTEGER | no |  |
| propiedades | antiguedad | INTEGER | no |  |
| propiedades | estado_conservacion | VARCHAR(20) | no |  |
| propiedades | acabados | VARCHAR(20) | no |  |
| propiedades | cochera | INTEGER | no |  |
| propiedades | jardin | BOOLEAN | no |  |
| propiedades | piscina | BOOLEAN | no |  |
| propiedades | ascensor | BOOLEAN | no |  |
| propiedades | seguridad | BOOLEAN | no |  |
| propiedades | cerca_colegios | BOOLEAN | no |  |
| propiedades | cerca_hospitales | BOOLEAN | no |  |
| propiedades | cerca_comercial | BOOLEAN | no |  |
| propiedades | transporte_publico | BOOLEAN | no |  |
| propiedades | precio | FLOAT | no |  |
| propiedades | estado | VARCHAR(15) | no |  |
| propiedades | motivo_rechazo | VARCHAR(300) | sí |  |
| propiedades | creado_en | DATETIME | no |  |
| propiedades | actualizado_en | DATETIME | no |  |
| favoritos | id | INTEGER | no | PK |
| favoritos | usuario_id | INTEGER | no | FK → usuarios.id |
| favoritos | propiedad_id | INTEGER | no | FK → propiedades.id |
| favoritos | creado_en | DATETIME | no |  |
| fotos | id | INTEGER | no | PK |
| fotos | propiedad_id | INTEGER | no | FK → propiedades.id |
| fotos | archivo | VARCHAR(120) | no |  |
| fotos | orden | INTEGER | no |  |
| mensajes | id | INTEGER | no | PK |
| mensajes | propiedad_id | INTEGER | no | FK → propiedades.id |
| mensajes | comprador_id | INTEGER | no | FK → usuarios.id |
| mensajes | autor_id | INTEGER | no | FK → usuarios.id |
| mensajes | contenido | TEXT | no |  |
| mensajes | leido | BOOLEAN | no |  |
| mensajes | creado_en | DATETIME | no |  |
| tasaciones | id | INTEGER | no | PK |
| tasaciones | usuario_id | INTEGER | no | FK → usuarios.id |
| tasaciones | modelo_id | INTEGER | sí | FK → modelos_ml.id |
| tasaciones | propiedad_id | INTEGER | sí | FK → propiedades.id |
| tasaciones | datos | JSON | no |  |
| tasaciones | precio_estimado | FLOAT | no |  |
| tasaciones | precio_min | FLOAT | no |  |
| tasaciones | precio_max | FLOAT | no |  |
| tasaciones | precio_m2 | FLOAT | no |  |
| tasaciones | factores | JSON | no |  |
| tasaciones | creado_en | DATETIME | no |  |
| visitas | id | INTEGER | no | PK |
| visitas | propiedad_id | INTEGER | no | FK → propiedades.id |
| visitas | comprador_id | INTEGER | no | FK → usuarios.id |
| visitas | fecha_hora | DATETIME | no |  |
| visitas | modalidad | VARCHAR(15) | no |  |
| visitas | comentario | VARCHAR(400) | sí |  |
| visitas | estado | VARCHAR(15) | no |  |
| visitas | respuesta | VARCHAR(300) | sí |  |
| visitas | creado_en | DATETIME | no |  |
