# Prueba manual QR-KIOSK-1A-2

Esta fase sólo valida la lectura técnica de un QR y la transición a
`RESOLVING`. No consulta Supabase ni confirma llegadas.

1. Inicie EVKOR Web y autentíquese con una sesión de desarrollo existente.
2. Abra `/app/kiosk`.
3. Conceda el permiso de cámara cuando el navegador lo solicite.
4. Compruebe que aparece el preview y el texto de escaneo, sin menú ni shell
   administrativo.
5. Presente un QR de cuatro caracteres alfanuméricos, por ejemplo `T3A1`.
6. Compruebe la transición `WELCOME_SCAN` a `RESOLVING` y el mensaje de espera.
7. Use **Continuar demo (simulacion)** sólo para recorrer las pantallas locales
   restantes; no existe resolución de invitación en esta fase.
8. En éxito, use **Finalizar / Volver al inicio** y compruebe que vuelve a
   escanear sin recargar la página.
9. Presente un segundo QR y compruebe que no hay tareas duplicadas, errores ni
   navegación a Llegadas.
10. Para probar un fallo de cámara, rechace el permiso o desconecte el dispositivo;
    use **Intentar nuevamente** y confirme que se inicia una sesión nueva.

`scripts/test_camera_web_spike.py` sigue siendo una prueba manual y no forma
parte de la batería automatizada.
