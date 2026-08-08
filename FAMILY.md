# FAMILY.md — La familia de arneses

## El principio, en una línea

Cada hermano responde a una pregunta distinta sobre el tiempo. El eje
del tiempo no es una metáfora decorativa — es la prueba de que dos
cosas son hermanos de verdad o solo se parecen por fuera.

```
PASADO/PRESENTE ──────► FUTURO (física) ──────► FUTURO (decisión) ──────► PRESENTE
   Percibir                 Predecir                 Planear                Gobernar
"¿dónde está,          "¿dónde estará,          "¿qué camino               "¿qué le llega
 ahora mismo?"           dado lo que sé            tomar, dado               al humano,
                          de física?"               lo que aún               en este instante?"
                                                      no sé con certeza?"
        ↑                      ↑                        ↑                       ↑
   World-facing           World-facing             World-facing            Human-facing
```

El framework no es una línea — es un loop. Los hermanos 1-3 miran
hacia afuera (al mundo): generan insights mirando al futuro para
comprar tiempo. El hermano 4 mira hacia adentro (al humano): gasta
ese tiempo entregando los insights en el momento justo. Gobernar
opera en la "Psychological Present" — la ventana de 100–500ms donde
un humano puede procesar un input. Sin esa ventana, la mejor
predicción del mundo llega demasiado tarde o demasiado temprano.

Percibir mira hacia atrás — observaciones ya ocurridas, para estimar
el presente. Predecir mira adelante con una certeza que se degrada
con la distancia (medido, no supuesto: la predicción cerca de un
rebote ya salió 6x peor que en vuelo libre — más futuro, más
incertidumbre, literal). Planear mira adelante también, pero sobre
algo que todavía no existe y depende de una elección — de otro
agente o del propio usuario. Gobernar vuelve al presente puro: no le
importa el futuro, solo qué hacer con la atención disponible ahora
mismo.

**La misma variable ya apareció antes, sin que la hubiéramos nombrado
así.** Touch (reflejo) es presente puro, cero tiempo de deliberación.
Voice es deliberativo — necesita que el tiempo se abra para existir.
William James distinguió atención voluntaria de automática en 1890,
desde la psicología. Hoy llegamos a la misma distinción desde las
matemáticas. No es coincidencia — es la misma pregunta, dos
disciplinas.

## Los hermanos

### 1. Percibir + Predecir (física) — `perception_factory`
**Estado:** construido. `core/tracker.py` (Kalman de aceleración
constante + detector de rebote), primera instancia `tennis_ball`
(sintética), 8/8 tests.
**Qué responde:** dado un objeto que obedece física conocida
(gravedad, restitución), ¿dónde está y dónde estará?
**Por qué es un problema tratable:** la física es conocida y no
cambia de opinión. El error es cuantificable y se reduce con buen
tuneo (verificado: 43% de reducción con Q/R corregido).
**Ejemplos que caen aquí:** pelota de tenis, billar, trayectoria de
salto libre antes de abrir el paracaídas.

### 2. Predecir (intención) — sin construir todavía
**Estado:** identificado, no diseñado. Nombre provisional:
`intent_factory`.
**Qué respondería:** dado OTRO humano tomando una decisión (¿va a
intentar pasarme?), ¿qué es probable que haga?
**Por qué NO es el mismo problema que el hermano 1, aunque se sienta
parecido:** una pelota obedece gravedad; un piloto obedece su propio
juicio. No hay ecuación física que gobierne una intención — el núcleo
no puede ser un filtro de Kalman. Esto es modelado de patrón de
comportamiento, con incertidumbre de una naturaleza distinta,
irreducible de la misma forma que el ruido de sensor.
**Ejemplo que cae aquí:** el auto rival en F1 decidiendo si intenta
el sobrepaso.

### 3. Planear — sin construir todavía
**Estado:** identificado, no diseñado. Nombre provisional:
`planning_factory`.
**Qué respondería:** dado un terreno o situación estática (viento,
topografía, obstáculos), ¿cuál es la mejor ruta — sugerida, nunca
impuesta?
**Por qué NO es el mismo problema que los hermanos 1 ni 2:** no hay
nada moviéndose que rastrear ni predecir — es optimización sobre un
espacio de posibilidades ya existente. El núcleo aquí se parece más a
algoritmos de búsqueda de ruta que a un filtro de estado.
**Ejemplo que cae aquí:** sugerir la ruta más segura en un salto
base, con la decisión final siempre del usuario.

### 4. Gobernar — `sensory_architecture_factory`
**Estado:** construido. Núcleo de arbitraje por prioridad/presupuesto,
mecanismo híbrido reactivo/proactivo, cuatro instancias (F1, tenis,
ciclismo, ENMAX), 133 tests, hook de verificación.
**Qué responde:** de todo lo que los otros tres hermanos saben o
predicen, ¿qué le llega al humano ahora mismo, y por qué canal?
**Es el único que mira al presente puro** — no genera predicciones
ni rutas, las consume de los otros hermanos (ese es el propósito del
slot `perception.py` que ya existe en cada instancia).

## Guardarraíles heredados (aplican a cualquier hermano, no solo al que los originó)

Cada uno de estos salió de un error real, no de precaución teórica —
por eso vale la pena que cualquier hermano nuevo los herede por
default, en vez de tener que redescubrirlos por su cuenta.

1. **Sesgo de automatización, en cualquier hermano que prediga
   comportamiento humano.** Antes de construir algo tipo
   `intent_factory`, probar si la herramienta mejora o empeora el
   juicio humano bajo presión de tiempo — "el usuario decide al
   final" no neutraliza el riesgo; la investigación muestra que la
   presión de tiempo empeora la sobre-confianza en la automatización,
   no la reduce.

2. **Un resultado sorprendente se revisa antes de reportarse como
   hallazgo.** El 6.7% de reducción de error en `perception_factory`
   no era un límite real del método — era Q/R mal calibrado. Un
   número sospechosamente bueno o malo se cuestiona primero, no se
   documenta como descubrimiento.

3. **Etiquetado de confianza obligatorio, mismo vocabulario en toda
   la familia.** REAL/PROXY/DECLARED en `sensory_architecture_factory`,
   MEASURED/TRACKED/PREDICTED en `perception_factory` — cualquier
   hermano nuevo declara su propio vocabulario equivalente antes de
   escribir código, y nunca mezcla lo medido con lo asumido.

4. **Ninguna autonomía total sin aprobación humana.** El principio
   híbrido de la revisión periódica (un agente investiga, un humano
   aprueba cualquier cambio real) aplica a cualquier hermano que
   tenga su propio mecanismo de auto-revisión — no solo al que lo
   originó.

5. **Nombres reales de terceros son una decisión consciente, no un
   default.** Usar el nombre de una empresa o institución real
   (ENMAX, Policía de Calgary) en material que sale del proyecto se
   decide a propósito cada vez, nunca por inercia.

6. **No pedir prestado prestigio de fuentes no verificables.** El
   mismo criterio que descartó el Kybalion aplica a cualquier
   referencia citada en cualquier hermano — se verifica antes de
   citar, nunca se inventa una fuente para sonar más fundamentado.

7. **El alcance no crece solo porque se puede.**

8. **El presupuesto temporal es una variable de primera clase.** Una
   predicción que llega después del evento es un fantasma. Cada
   hermano debe exponer su latencia de cómputo antes de integrarse
   con los demás. Si `intent_factory` tarda 200ms en clasificar un
   comportamiento, pero `perception_factory` dice que el evento
   ocurre en 150ms, `sensory_architecture_factory` debe saber ignorar
   la intención y disparar el reflejo (Touch) de inmediato. La
   latencia no es un detalle de implementación — es un invariante del
   contrato entre hermanos. (Guardarraíl surgido de revisión externa
   del consejo LLM, agosto 2026.) Cuando quien
   construye (Claude Code u otro) agrega capacidad no pedida, se
   revisa a propósito antes de aceptarla — no se acepta por default
   solo porque ya está hecha.

## La regla para cuando lleguen más hermanos

Antes de construir algo nuevo, una sola pregunta: **¿en cuál de las
cuatro cajas cae — Percibir/Predecir física, Predecir intención,
Planear, o Gobernar?**

- Si cae limpio en una ya existente: es una instancia nueva de ese
  arnés, no un hermano nuevo (ej. video real de tenis en vez de
  sintético — sigue siendo `perception_factory`).
- Si no cae limpio en ninguna: es señal de pausar y diseñar el
  núcleo nuevo con cuidado, no de forzarlo dentro de uno que ya
  existe — exactamente el error que se evitó cuando `agents/` y
  `api/` casi se cuelan dentro de `sensory_architecture_factory` sin
  pedirlo.
- Ninguna caja se construye "porque ya se pudo con la anterior." Cada
  una tiene su propio `CONTRACT.md`, sus propias pruebas, y su propio
  hallazgo honesto antes de llamarse terminada — mismo estándar que
  ya se aplicó dos veces.
