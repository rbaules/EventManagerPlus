## Compatibilidad del entorno

- El proyecto utiliza Python 3.14.6.
- Utilizar siempre `env\Scripts\python.exe`.
- No utilizar el Python global.
- El proyecto utiliza Flet 0.85.3 hasta que exista una decision explicita de actualizacion.
- Excluir `env`, `.git` y `__pycache__` de busquedas y modificaciones.
- No editar archivos dentro de `env\Lib\site-packages`.
- Validar la API de Flet contra la version instalada antes de escribir codigo.
- No utilizar ejemplos correspondientes a versiones antiguas de Flet.
- No cambiar versiones de dependencias sin justificarlo y sin aprobacion.
- Antes de declarar terminada una tarea, ejecutar `pip check`, compilacion y una prueba controlada.
- Toda modificacion de codigo Flet debe incluir validacion de las clases, constantes, propiedades y parametros utilizados.
