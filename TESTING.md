# Probar Planet El Margen gratis, antes de montar un servidor propio

Blogger no sirve como entorno de pruebas porque no ejecuta código del lado
del servidor (ni Python, ni cron): solo admite plantillas HTML/CSS/JS y
gadgets propios de Google.

La alternativa gratuita que más se parece a tener tu propio servidor —
sin administrar nada todavía — es **GitHub Actions + GitHub Pages**:
GitHub ejecuta `planet.py` en un runner cada hora (como haría tu cron) y
publica el `output/` resultante en una URL pública gratuita del tipo
`https://tuusuario.github.io/planet-elmargen/`.

## Pasos

1. **Crea una cuenta en GitHub** (gratis) si no tienes una: https://github.com/join

2. **Crea un repositorio nuevo**, por ejemplo `planet-elmargen`, público
   (los repos públicos tienen GitHub Pages gratis sin límites prácticos
   para un proyecto de este tamaño).

3. **Sube todos los archivos del proyecto** (los que ya tienes: `planet.py`,
   `feeds.txt`, `requirements.txt`, `templates/`, `static/`, y ahora también
   `.github/workflows/build.yml`, incluido en este mensaje). Puedes hacerlo
   arrastrando los archivos en la interfaz web de GitHub, o por línea de
   comandos:

   ```bash
   cd planet-elmargen
   git init
   git add .
   git commit -m "Primera versión de Planet El Margen"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/planet-elmargen.git
   git push -u origin main
   ```

4. **Activa GitHub Pages con origen "GitHub Actions"**: en el repositorio,
   ve a `Settings → Pages` y en "Build and deployment → Source" elige
   **"GitHub Actions"** (no "Deploy from a branch").

5. **Lanza el workflow manualmente la primera vez**: ve a la pestaña
   `Actions` del repositorio, entra en "Regenerar y publicar Planet El
   Margen" y pulsa "Run workflow". Tarda menos de un minuto.

6. **Consulta tu sitio de pruebas** en la URL que aparece en
   `Settings → Pages` (algo como
   `https://tuusuario.github.io/planet-elmargen/`). A partir de ahora se
   regenerará solo cada hora (lo puedes ajustar cambiando la línea `cron`
   del workflow), y también cada vez que hagas `git push` con cambios en
   `feeds.txt`.

## Qué prueba y qué no prueba este entorno

Prueba de verdad:
- Que `planet.py` lee los feeds y genera el HTML correctamente.
- El diseño y el CSS, en una URL pública real.
- La automatización periódica (el equivalente al cron/systemd que usarás luego).

No prueba (porque GitHub Pages lo gestiona por ti):
- La configuración de nginx/Apache.
- El certificado HTTPS y el dominio propio (aunque GitHub Pages también
  permite conectar un dominio propio como `elmargen.net` si quisieras
  quedarte aquí en vez de montar servidor).

## Cuando quieras pasar a tu propio servidor

No hace falta reescribir nada: `planet.py`, `feeds.txt`, `templates/` y
`static/` son exactamente los mismos archivos. Simplemente dejas de
depender del workflow de GitHub Actions y usas el cron o el systemd timer
descritos en `README.md`, apuntando nginx a tu propia carpeta `output/`.
