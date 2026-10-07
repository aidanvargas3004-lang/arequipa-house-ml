-- ============================================================================
-- Arequipa House ML · PASO 1: crear usuario y base de datos
-- Ejecutar conectado como "postgres" (en pgAdmin: Query Tool sobre el servidor).
-- Ejecuta CADA sentencia por separado (CREATE DATABASE no admite transacciones).
-- ============================================================================

-- 1) Usuario de la aplicación (cambia la clave; usa solo letras y números)
CREATE USER arequipa WITH PASSWORD 'ClaveSegura123';

-- 2) Base de datos (propiedad del usuario anterior)
CREATE DATABASE arequipa_house OWNER arequipa ENCODING 'UTF8' TEMPLATE template0;
