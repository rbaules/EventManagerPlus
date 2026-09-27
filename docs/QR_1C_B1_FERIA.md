# QR-1C-B1 para la feria

QR-1C-B1 original ya estaba instalado en Supabase mediante la migracion
historica `202609150001`. La normalizacion de feria se entrega por la migracion
incremental `202609270001`, sin reescribir aquella migracion aplicada.

Los codigos QR ya fueron generados y distribuidos externamente. Durante la
feria, las RPC administrativas reciben `p_codigo`, normalizan espacios
accidentales y mayusculas/minusculas, y aceptan solo `[A-Z0-9]{4}`. No generan
ni reemplazan codigos automaticamente.

El espacio de 36^4 codigos es reducido; el codigo no debe tratarse como una
credencial criptograficamente fuerte. Esta excepcion es temporal por las
invitaciones ya entregadas. Las RPC administrativas exigen autenticacion,
rol, cuenta y evento; QR-2 debera rechazar codigos Revocados.

TODO posterior a la feria: evaluar una migracion compatible a tokens largos,
aleatorios y generados de forma segura. La futura importacion Excel debe
asociar el codigo externo en el flujo administrativo de invitaciones, usando
estas mismas reglas de formato, unicidad y alcance; no forma parte de QR-1C-B1.
