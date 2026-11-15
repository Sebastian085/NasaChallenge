# Explorador de Marte

Visor web 3D del relieve MOLA y planificador de rutas experimental. La aplicación carga sus dependencias gráficas desde Internet y las teselas de elevación desde `MOLA-tiles/`.

## Contenido del repositorio

- `a.html`: visor 3D y planificador.
- `prepare_mola.py`: generador local de teselas MOLA.
- `requirements.txt`: dependencias de Python para generar las teselas.
- `MOLA-raw/`: datos fuente locales; no se incluyen en Git.
- `MOLA-tiles/`: datos generados localmente; no se incluyen en Git.

Los datos fuente y las teselas ocupan varios gigabytes. Cada computadora debe tener su propia copia de `MOLA-raw/` y generar `MOLA-tiles/` después de clonar o actualizar el repositorio. Git ignora ambas carpetas.

## Requisitos

- Python 3.10 o posterior.
- Navegador moderno con WebGL.
- Conexión a Internet para cargar Three.js desde jsDelivr.
- Espacio libre suficiente: como referencia, los datos fuente usados actualmente ocupan unos 2,7 GB y las teselas generadas unos 2,5 GB. Reserva espacio adicional durante el procesamiento.

## Preparar los datos MOLA

1. Obtén los productos de topografía MOLA MEGDR (archivos `MEGT`, no `MEGC`) y sus etiquetas PDS `.LBL`, desde NASA PDS Geosciences Node.
2. En la raíz de este proyecto, crea `MOLA-raw/` y coloca directamente dentro los 18 pares `.IMG`/`.LBL`: 16 productos globales `megt*hb` y los dos polares `megt_n_512_1` y `megt_s_512_1`.
3. No anides los archivos en otra carpeta. La ruta esperada queda así:

   ```text
   Explorador-Marte/
   ├── a.html
   ├── prepare_mola.py
   └── MOLA-raw/
       ├── megt... (16 archivos globales .IMG y sus .LBL)
       ├── megt_n_512_1.img
       ├── megt_n_512_1.lbl
       ├── megt_s_512_1.img
       └── megt_s_512_1.lbl
   ```

   Los nombres reales de los 16 productos globales comienzan con `megt` y terminan en `hb.img`/`hb.lbl`. Se necesitan tanto los `.IMG` como sus `.LBL`.

## Instalar dependencias y generar teselas

Ejecuta estos comandos desde la carpeta raíz del proyecto.

### Windows (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python prepare_mola.py
```

Si PowerShell bloquea la activación del entorno, ejecuta los comandos de instalación y generación con el intérprete del entorno, sin activarlo:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe prepare_mola.py
```

### macOS y Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python prepare_mola.py
```

El generador lee `MOLA-raw/` y crea `MOLA-tiles/` en la raíz del proyecto. El proceso puede tardar y requiere varios gigabytes libres. No subas ninguna de esas dos carpetas al repositorio.

Si guardaste los datos fuente en otra ubicación, indica la ruta de entrada y conserva la salida con el nombre esperado por el visor:

```text
python prepare_mola.py --input "RUTA/A/MOLA-raw" --output "MOLA-tiles"
```

En Windows, sustituye la ruta por una ruta de PowerShell, por ejemplo `D:\Datos\MOLA-raw`.

## Ejecutar el visor

El HTML utiliza módulos JavaScript; no lo abras haciendo doble clic. Desde la raíz del proyecto, inicia un servidor HTTP local:

```text
python -m http.server 8000
```

Abre `http://localhost:8000/a.html` en el navegador. Para detener el servidor, pulsa `Ctrl+C` en la terminal.

## Actualizar desde Git en otra computadora

Clona el repositorio una vez:

```text
git clone URL_DEL_REPOSITORIO
cd Explorador-Marte
```

Para obtener cambios posteriores:

```text
git pull
```

Después de cada clonación nueva, coloca los datos en `MOLA-raw/`, instala las dependencias de Python y genera `MOLA-tiles/`. Esos datos locales no llegan con `git pull`.

## Notas sobre los datos y el prototipo

- El generador valida las dimensiones y los tipos descritos por las etiquetas PDS y aplica la escala y el desplazamiento de los productos polares.
- Las teselas se codifican como RGB24 sin pérdida, con alturas en metros según la fórmula documentada en el manifiesto generado.
- MOLA global tiene resolución aproximada de 460 m por píxel; no resuelve rocas ni peligros locales.
- El planificador y los parámetros de vehículo son demostrativos; no están validados ni certificados para operaciones de misión.
