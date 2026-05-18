"""BauPilot — Tag- und Dokument-Tag-Operations (B-013, Roadmap E11).

Stellt drei Endpunkte bereit:
  GET    /api/v1/tags                          alle Tags des Mandanten (mit Hierarchie)
  POST   /api/v1/dokumente/{id}/tags           Tag an ein Dokument haengen
  DELETE /api/v1/dokumente/{id}/tags/{tag_id}  Tag entfernen

Die Tabellen kommen aus Migration 008: tenant.tags (mit parent_id und
ist_kategorie_wurzel) und tenant.dokument_tags (m:n).
"""

from tags.router import router as tags_router

__all__ = ["tags_router"]
