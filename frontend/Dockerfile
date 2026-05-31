FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY BAUPILOT.png /usr/share/nginx/html/BAUPILOT.png
# Statische Daten-Assets fuer Netzplan + Nullterminplan (B-013 POC).
# Werden bei jedem Build mitkopiert, damit sie nach Container-Restart erhalten bleiben.
COPY data /usr/share/nginx/html/data
EXPOSE 80