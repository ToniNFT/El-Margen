# Planet El Margen

Agregador de feeds RSS/Atom autoalojado. Sustituye al widget "Lista de
blogs" de Blogger: lee una lista de feeds, coge la última entrada de cada
uno y genera una página HTML estática. Sin base de datos, sin backend
corriendo permanentemente — un script que se ejecuta cada cierto tiempo y
un servidor web que sirve el HTML resultante.

## 1. Requisitos

- Un servidor (VPS, Raspberry Pi, hosting con acceso SSH...) con Python 3.9+
- Acceso de salida a internet (para descargar los feeds)
- Un servidor web para servir el HTML: nginx, Apache o incluso Caddy

## 2. Instalación

```bash
# Clona o copia esta carpeta al servidor, por ejemplo en /opt/planet-elmargen
cd /opt/planet-elmargen

# Crea un entorno virtual para no mezclar dependencias con el sistema
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## 3. Configuración

Edita `feeds.txt` y pon un feed por línea (el feed RSS/Atom de cada blog
que quieras seguir, no la URL del blog). Las líneas que empiezan por `#`
se ignoran, úsalas para comentarios.

Si quieres ajustar el título, la bajada de portada, cuántas entradas
mostrar por blog o el total de entradas en la página, esas opciones están
al principio de `planet.py`:

```python
SITE_TITLE = "El Margen"
SITE_TAGLINE = "Conspiraciones. Contrainformación. Paranoias..."
ENTRIES_PER_FEED = 1
MAX_TOTAL_ENTRIES = 80
```

## 4. Generar la página manualmente (prueba)

```bash
source venv/bin/activate
python3 planet.py
```

Esto crea `output/index.html` y copia `output/style.css`. Ábrelo en el
navegador para comprobar que todo se ve bien antes de automatizarlo.

## 5. Servir el HTML con nginx

Ejemplo de bloque de servidor mínimo:

```nginx
server {
    listen 80;
    server_name elmargen.net www.elmargen.net;

    root /opt/planet-elmargen/output;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }
}
```

Recarga nginx: `sudo nginx -t && sudo systemctl reload nginx`.

Para HTTPS, la forma más sencilla es Certbot:

```bash
sudo certbot --nginx -d elmargen.net -d www.elmargen.net
```

## 6. Automatizar la actualización

Elige una de las dos opciones (no hacen falta ambas).

### Opción A: cron (más simple)

```bash
crontab -e
```

Añade una línea para regenerar la página cada 30 minutos:

```cron
*/30 * * * * /opt/planet-elmargen/venv/bin/python3 /opt/planet-elmargen/planet.py >> /var/log/planet-elmargen.log 2>&1
```

### Opción B: systemd timer (más robusto, mejor para ver logs con journalctl)

Crea `/etc/systemd/system/planet-elmargen.service`:

```ini
[Unit]
Description=Regenerar Planet El Margen

[Service]
Type=oneshot
WorkingDirectory=/opt/planet-elmargen
ExecStart=/opt/planet-elmargen/venv/bin/python3 /opt/planet-elmargen/planet.py
```

Crea `/etc/systemd/system/planet-elmargen.timer`:

```ini
[Unit]
Description=Ejecutar Planet El Margen cada 30 minutos

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min

[Install]
WantedBy=timers.target
```

Actívalo:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now planet-elmargen.timer
sudo systemctl list-timers | grep planet   # comprobar que está programado
journalctl -u planet-elmargen.service      # ver los logs de cada ejecución
```

## 7. Mantenimiento

- **Añadir o quitar blogs**: edita `feeds.txt` y espera a la siguiente
  ejecución (o lánzala a mano con `python3 planet.py`).
- **Un feed da error**: el script lo salta y sigue con los demás; revisa
  el log para ver cuál falló y por qué (URL caída, XML mal formado, etc.).
- **Cambiar el estilo**: todo el CSS vive en `static/style.css`, sin
  frameworks externos.
- **Copia de seguridad**: no hay base de datos que respaldar — con
  guardar `feeds.txt` y la carpeta del proyecto es suficiente.

## Estructura del proyecto

```
planet-elmargen/
├── planet.py              # script principal
├── feeds.txt               # lista de feeds a seguir
├── requirements.txt
├── templates/
│   └── index.html.jinja    # plantilla de la página
├── static/
│   └── style.css           # estilos
└── output/                 # se genera solo — esto es lo que sirve nginx
    ├── index.html
    └── style.css
```
