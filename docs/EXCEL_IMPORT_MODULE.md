# Módulo de importación Excel (Tarea 7B)

## Alcance

El módulo existe solo en FULL para Master y Administrador, con usuario, cuenta
y evento activos, acceso al evento, estado `Activo` y fase `Pre_evento`. 7C
prepara una única RPC transaccional; el entorno no podrá importar hasta aplicar
manualmente la migración documentada en `EXCEL_IMPORT_RPC.md`.

## Dependencia y plantilla

Se validó `openpyxl==3.1.5` con Python 3.14.6. La plantilla se genera sin
Supabase, contiene `Importación` e `Instrucciones`, nueve columnas canónicas,
autofiltro, encabezado congelado, formatos de texto y lista Sí/No. La descarga
usa los bytes de `FilePicker.save_file`: el navegador no recibe rutas del
servidor y desktop escribe solo en la ruta elegida por el usuario.

## Lectura, límites y seguridad

- Solo `.xlsx`, contenido ZIP/XLSX real, sin macros ni ejecución de fórmulas.
- Apertura `read_only=True`, `data_only=True`, `keep_links=False` y una segunda
  lectura sin `data_only` para rechazar fórmulas; ambos workbooks se cierran.
- Máximo configurable: 5 MiB y 5.000 filas.
- El nombre se reduce a nombre base y se rechaza path traversal.
- La carga web usa bytes en memoria; no crea archivos predecibles compartidos.
- El CSV de errores es UTF-8 con BOM, usa `csv.writer`, trunca/sanitiza valores
  y antepone apóstrofo a `=`, `+`, `-` y `@`.

## Normalización y validación

Se conservan como texto códigos, teléfonos y Mesa ID. Email pasa a minúsculas;
principal acepta Sí/Si/No ignorando caso y acento. Los nombres comparables usan
trim, espacios colapsados, minúsculas y eliminación de acentos, equivalente a
`evp_normalizar_texto`. Se conservan los valores visibles.

Se validan requeridos y longitudes del esquema, orden entero positivo y único,
exactamente un principal y un destinatario por invitación, nombre de invitado
único en todo el archivo, coherencia Mesa ID/nombre y unicidad del nombre de
mesa normalizado. Invitados sin mesa son válidos. Las filas vacías finales se
ignoran y las intermedias generan advertencia.

## Vista previa y errores

La vista presenta contexto, archivo, procesamiento, seis contadores, hasta 100
filas, primeras 20 incidencias y descarga del CSV. Una consulta de solo lectura
comprueba las tres tablas; si existe cualquier dato muestra: “Este evento ya
contiene información y no admite importación inicial.”

## Pruebas

`scripts/test_excel_import.py` cubre dependencia/plantilla, estructura XLSX,
archivos dañados y límites, encabezados, normalización, invitaciones, mesas,
duplicados, contexto, capacidades, construcción UI, path traversal y CSV
injection. La prueba manual en navegador/Excel queda a cargo del usuario.
