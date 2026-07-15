# EVENTPLUS_BRAND_ASSETS.md

## 1. Propósito

Este archivo define los activos visuales oficiales de EventPlus que Codex debe usar al crear o modificar pantallas Flet.

Codex debe leer este archivo junto con:

```text
EVENTPLUS_CONTEXT.md
EVENTPLUS_SCHEMA_CONTEXT_v1_1.md
EVENTPLUS_UI_UX_GUIDELINES.md
EVENTPLUS_MVP_SCOPE_AND_CODEX_RULES_v1_0.md
```

---

## 2. Archivos oficiales de logo

Los logos oficiales deben guardarse en:

```text
assets/brand/EventPlus_logo_v2.0_horizontal.png
assets/brand/EventPlus_logo_v2.1_stacked.png
```

Ambos archivos son PNG con fondo transparente.

### Logo horizontal

```text
assets/brand/EventPlus_logo_v2.0_horizontal.png
```

Uso recomendado:

- AppBar / encabezado.
- Login en pantallas amplias.
- Splash o portada horizontal.
- Documentos o pantallas donde haya suficiente ancho.

### Logo apilado / compacto

```text
assets/brand/EventPlus_logo_v2.1_stacked.png
```

Uso recomendado:

- Pantalla de login.
- Tarjeta central de bienvenida.
- Espacios más compactos.
- Pantallas donde convenga mayor presencia vertical del logo.

---

## 3. Regla de uso en Flet

La app debe declarar el directorio de assets al iniciar:

```python
if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
```

Las rutas usadas por controles como `ft.Image` deben ser relativas a la carpeta `assets`.

Ejemplo correcto de uso en la versión actual de Flet:

```python
ft.Image(
    src="brand/EventPlus_logo_v2.0_horizontal.png",
    width=220,
    fit=ft.BoxFit.CONTAIN,
)
```

Ejemplo para login:

```python
ft.Image(
    src="brand/EventPlus_logo_v2.1_stacked.png",
    width=260,
    fit=ft.BoxFit.CONTAIN,
)
```

---

## 4. Corrección importante de compatibilidad Flet

No usar:

```python
ft.BoxFit.CONTAIN
```

Usar:

```python
ft.BoxFit.CONTAIN
```

Motivo:

En la versión actual de Flet, la propiedad `fit` de `ft.Image` usa `BoxFit`.

Si Codex encuentra código con:

```python
fit=ft.BoxFit.CONTAIN
```

debe reemplazarlo por:

```python
fit=ft.BoxFit.CONTAIN
```

---

## 5. Reglas para Codex

Codex debe respetar estas reglas:

1. Usar los logos oficiales ubicados en `assets/brand/`.
2. No recrear el logo con texto, iconos ni controles Flet.
3. No cambiar colores del logo desde código.
4. No deformar el logo.
5. Mantener proporción usando `fit=ft.BoxFit.CONTAIN`.
6. No usar fondos oscuros o saturados que reduzcan la legibilidad del texto negro del logo.
7. Si se usa en modo oscuro, colocar el logo sobre una tarjeta o contenedor claro, o usar una versión del logo preparada para fondo oscuro si se crea más adelante.
8. No aplicar sombras exageradas, filtros o efectos al logo.
9. No usar el logo como botón si puede confundirse con una acción.
10. No guardar rutas absolutas como `C:\...` dentro del código.

---

## 6. Recomendación de layout

### Login

Usar el logo apilado/compacto:

```text
assets/brand/EventPlus_logo_v2.1_stacked.png
```

Layout sugerido:

```text
Card centrada
Logo
Título breve
Texto de apoyo
Botón "Iniciar sesión con Google"
Estado / mensaje de validación
```

### Pantallas internas

Usar el logo horizontal cuando haya espacio:

```text
assets/brand/EventPlus_logo_v2.0_horizontal.png
```

En AppBar o encabezado:

- Mantener tamaño moderado.
- No competir con el nombre del evento actual.
- El evento actual debe seguir siendo visible.

---

## 7. Tamaños sugeridos

```text
Login desktop/tablet: 240-320 px de ancho
Login móvil: 180-240 px de ancho
AppBar desktop: 140-220 px de ancho
AppBar móvil: 120-160 px de ancho
```

Evitar anchos fijos rígidos si el layout debe ser responsivo.

---

## 8. Paleta visual asociada

El logo utiliza verde EventPlus y texto negro.

La interfaz debe mantener una paleta sobria:

```text
Color primario: verde EventPlus
Neutros: blanco, gris claro, gris medio, gris oscuro
Éxito: verde
Advertencia: ámbar/naranja
Error: rojo
Información: azul discreto
```

No saturar las pantallas con muchos verdes distintos. El logo debe ser el principal elemento de marca.

---

## 9. Reglas para modo claro y modo oscuro

El logo tiene texto negro. Por eso:

### Modo claro

Puede usarse directamente sobre fondo blanco o gris muy claro.

### Modo oscuro

No colocar directamente sobre fondo negro u oscuro si reduce legibilidad.

Usar una de estas opciones:

```text
Contenedor blanco o superficie clara
Tarjeta con fondo claro
Versión alternativa del logo para modo oscuro, si se crea en el futuro
```

---

## 10. Estructura recomendada del proyecto

```text
EVENTPLUS/
│
├── app.py
├── .env
├── EVENTPLUS_CONTEXT.md
├── EVENTPLUS_SCHEMA_CONTEXT_v1_1.md
├── EVENTPLUS_UI_UX_GUIDELINES.md
├── EVENTPLUS_MVP_SCOPE_AND_CODEX_RULES_v1_0.md
├── EVENTPLUS_BRAND_ASSETS.md
│
├── assets/
│   └── brand/
│       ├── EventPlus_logo_v2.0_horizontal.png
│       └── EventPlus_logo_v2.1_stacked.png
│
├── services/
├── views/
├── components/
└── utils/
```

---

## 11. Instrucción obligatoria para Codex

Antes de crear o modificar pantallas, Codex debe considerar:

```text
EVENTPLUS_BRAND_ASSETS.md
EVENTPLUS_UI_UX_GUIDELINES.md
```

Cuando cree la pantalla de login o el App Shell, debe usar uno de los logos oficiales desde `assets/brand/` y debe usar `ft.BoxFit.CONTAIN`, no la constante antigua de ajuste de imagen.
