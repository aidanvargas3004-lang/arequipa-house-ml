-- ============================================================================
-- Arequipa House ML · PASO 2: crear las 11 tablas
-- Ejecutar CONECTADO A LA BASE "arequipa_house" (no a "postgres").
-- En pgAdmin: clic derecho sobre arequipa_house → Query Tool → pegar o abrir
-- este archivo → ▶ Ejecutar (F5).
-- Si la base ya tiene tablas, primero ejecuta el bloque "REINICIO" (abajo).
-- ============================================================================

-- Las tablas quedan a nombre del usuario de la aplicación
SET ROLE arequipa;

-- ---------------------------------------------------------------------------
-- REINICIO (opcional, BORRA TODO). Quita los "--" de las 2 líneas para usarlo.
-- DROP SCHEMA public CASCADE;
-- CREATE SCHEMA public AUTHORIZATION arequipa;
-- ---------------------------------------------------------------------------

CREATE TABLE ajustes_distrito (
	distrito VARCHAR(60) NOT NULL, 
	factor FLOAT NOT NULL, 
	PRIMARY KEY (distrito)
);


CREATE TABLE dataset_registros (
	id SERIAL NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	distrito VARCHAR(60) NOT NULL, 
	area_terreno FLOAT NOT NULL, 
	area_construida FLOAT NOT NULL, 
	habitaciones INTEGER NOT NULL, 
	banos INTEGER NOT NULL, 
	pisos INTEGER NOT NULL, 
	antiguedad INTEGER NOT NULL, 
	estado_conservacion VARCHAR(20) NOT NULL, 
	acabados VARCHAR(20) NOT NULL, 
	cochera INTEGER NOT NULL, 
	jardin INTEGER NOT NULL, 
	piscina INTEGER NOT NULL, 
	ascensor INTEGER NOT NULL, 
	seguridad INTEGER NOT NULL, 
	cerca_colegios INTEGER NOT NULL, 
	cerca_hospitales INTEGER NOT NULL, 
	cerca_comercial INTEGER NOT NULL, 
	transporte_publico INTEGER NOT NULL, 
	precio FLOAT NOT NULL, 
	origen VARCHAR(15) NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_dataset_registros_distrito ON dataset_registros (distrito);
CREATE INDEX ix_dataset_registros_origen ON dataset_registros (origen);
CREATE INDEX ix_dataset_registros_tipo ON dataset_registros (tipo);

CREATE TABLE parametros (
	clave VARCHAR(60) NOT NULL, 
	valor VARCHAR(60) NOT NULL, 
	descripcion VARCHAR(200) NOT NULL, 
	PRIMARY KEY (clave)
);


CREATE TABLE usuarios (
	id SERIAL NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	email VARCHAR(160) NOT NULL, 
	telefono VARCHAR(30), 
	password_hash VARCHAR(255) NOT NULL, 
	rol VARCHAR(20) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	intentos_fallidos INTEGER NOT NULL, 
	bloqueado_hasta TIMESTAMP WITHOUT TIME ZONE, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	ultimo_acceso TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_usuarios_email ON usuarios (email);

CREATE TABLE modelos_ml (
	id SERIAL NOT NULL, 
	version INTEGER NOT NULL, 
	algoritmo VARCHAR(30), 
	archivo VARCHAR(120), 
	estado VARCHAR(12) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	metricas JSON, 
	composicion JSON, 
	error VARCHAR(400), 
	creado_por_id INTEGER, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	terminado_en TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (version), 
	FOREIGN KEY(creado_por_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_modelos_ml_activo ON modelos_ml (activo);

CREATE TABLE propiedades (
	id SERIAL NOT NULL, 
	vendedor_id INTEGER NOT NULL, 
	titulo VARCHAR(160) NOT NULL, 
	descripcion TEXT NOT NULL, 
	direccion VARCHAR(200) NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	distrito VARCHAR(60) NOT NULL, 
	area_terreno FLOAT NOT NULL, 
	area_construida FLOAT NOT NULL, 
	habitaciones INTEGER NOT NULL, 
	banos INTEGER NOT NULL, 
	pisos INTEGER NOT NULL, 
	antiguedad INTEGER NOT NULL, 
	estado_conservacion VARCHAR(20) NOT NULL, 
	acabados VARCHAR(20) NOT NULL, 
	cochera INTEGER NOT NULL, 
	jardin BOOLEAN NOT NULL, 
	piscina BOOLEAN NOT NULL, 
	ascensor BOOLEAN NOT NULL, 
	seguridad BOOLEAN NOT NULL, 
	cerca_colegios BOOLEAN NOT NULL, 
	cerca_hospitales BOOLEAN NOT NULL, 
	cerca_comercial BOOLEAN NOT NULL, 
	transporte_publico BOOLEAN NOT NULL, 
	precio FLOAT NOT NULL, 
	estado VARCHAR(15) NOT NULL, 
	motivo_rechazo VARCHAR(300), 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	actualizado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(vendedor_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_propiedades_distrito ON propiedades (distrito);
CREATE INDEX ix_propiedades_estado ON propiedades (estado);
CREATE INDEX ix_propiedades_precio ON propiedades (precio);
CREATE INDEX ix_propiedades_tipo ON propiedades (tipo);
CREATE INDEX ix_propiedades_vendedor_id ON propiedades (vendedor_id);

CREATE TABLE favoritos (
	id SERIAL NOT NULL, 
	usuario_id INTEGER NOT NULL, 
	propiedad_id INTEGER NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_favorito UNIQUE (usuario_id, propiedad_id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id), 
	FOREIGN KEY(propiedad_id) REFERENCES propiedades (id)
);

CREATE INDEX ix_favoritos_propiedad_id ON favoritos (propiedad_id);
CREATE INDEX ix_favoritos_usuario_id ON favoritos (usuario_id);

CREATE TABLE fotos (
	id SERIAL NOT NULL, 
	propiedad_id INTEGER NOT NULL, 
	archivo VARCHAR(120) NOT NULL, 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(propiedad_id) REFERENCES propiedades (id)
);

CREATE INDEX ix_fotos_propiedad_id ON fotos (propiedad_id);

CREATE TABLE mensajes (
	id SERIAL NOT NULL, 
	propiedad_id INTEGER NOT NULL, 
	comprador_id INTEGER NOT NULL, 
	autor_id INTEGER NOT NULL, 
	contenido TEXT NOT NULL, 
	leido BOOLEAN NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(propiedad_id) REFERENCES propiedades (id), 
	FOREIGN KEY(comprador_id) REFERENCES usuarios (id), 
	FOREIGN KEY(autor_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_mensajes_comprador_id ON mensajes (comprador_id);
CREATE INDEX ix_mensajes_creado_en ON mensajes (creado_en);
CREATE INDEX ix_mensajes_propiedad_id ON mensajes (propiedad_id);

CREATE TABLE tasaciones (
	id SERIAL NOT NULL, 
	usuario_id INTEGER NOT NULL, 
	modelo_id INTEGER, 
	propiedad_id INTEGER, 
	datos JSON NOT NULL, 
	precio_estimado FLOAT NOT NULL, 
	precio_min FLOAT NOT NULL, 
	precio_max FLOAT NOT NULL, 
	precio_m2 FLOAT NOT NULL, 
	factores JSON NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id), 
	FOREIGN KEY(modelo_id) REFERENCES modelos_ml (id), 
	FOREIGN KEY(propiedad_id) REFERENCES propiedades (id)
);

CREATE INDEX ix_tasaciones_creado_en ON tasaciones (creado_en);
CREATE INDEX ix_tasaciones_usuario_id ON tasaciones (usuario_id);

CREATE TABLE visitas (
	id SERIAL NOT NULL, 
	propiedad_id INTEGER NOT NULL, 
	comprador_id INTEGER NOT NULL, 
	fecha_hora TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	modalidad VARCHAR(15) NOT NULL, 
	comentario VARCHAR(400), 
	estado VARCHAR(15) NOT NULL, 
	respuesta VARCHAR(300), 
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(propiedad_id) REFERENCES propiedades (id), 
	FOREIGN KEY(comprador_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_visitas_comprador_id ON visitas (comprador_id);
CREATE INDEX ix_visitas_estado ON visitas (estado);
CREATE INDEX ix_visitas_propiedad_id ON visitas (propiedad_id);

-- Permisos explícitos para el usuario de la aplicación
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO arequipa;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO arequipa;

RESET ROLE;

-- Verificación: debe listar 11 tablas
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;
