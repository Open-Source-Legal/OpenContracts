# Legal AI Workspace MVP auf Basis von OpenContracts

Analyse-Stand: lokaler Checkout `feature/legal-ai-workspace-mvp`.

## 1. Kurzfazit zur Machbarkeit

OpenContracts ist als Grundlage fuer eine anwaltliche Legal-AI-Workspace sehr gut geeignet. Die Plattform bringt bereits die schwersten Bausteine mit: Dokumenten- und Corpusverwaltung, Annotationen, strukturierte Extraktion, Zitate/Quellen, GraphQL-API, Objektberechtigungen, Agenten, LLM-Provider, MCP-Server, WebSocket-Chat und einen komplexen Dokumentenarbeitsplatz.

Die pragmatische Strategie ist kein Rewrite und keine separate UI, sondern ein inkrementeller Umbau:

1. Begriffe und Navigation auf Kanzlei-Workflows umstellen.
2. Die vorhandene Dokumentenansicht zur Akten-/Pruefungsansicht ausbauen.
3. AI-Aktionen als erste Produktfunktionen auf vorhandenen Agenten, Extracts, Analyses und CorpusActions aufsetzen.
4. Schriftsatz- und DOCX-Export als kleinen neuen Backend-Pfad ergaenzen, statt den bestehenden Corpus-Export zu verbiegen.

## 2. OpenContracts-Architektur

Backend:

- Django-Projekt mit Apps fuer `documents`, `corpuses`, `annotations`, `extracts`, `analyzer`, `conversations`, `agents`, `worker_uploads`, `document_imports`, `discovery`, `benchmarks` und `research`.
- GraphQL ueber Graphene-Django in `config/graphql`, plus einzelne REST/WebSocket-Pfade.
- Hintergrundverarbeitung ueber Celery, Redis und Channels/Daphne.
- Objektberechtigungen ueber Django Guardian und servicebasierte `visible_to_user`-/Permission-Checks.
- Speicher ist konfigurierbar fuer lokal, AWS oder GCP.
- LLM-Framework basiert auf PydanticAI mit eigenen Provider-Adaptern.
- MCP ist vorhanden und kann OpenContracts-Funktionen externen Agenten bereitstellen.

Frontend:

- React 18, TypeScript, Vite, Apollo Client, React Router, styled-components.
- Zentrale UI-Bausteine ueber `@os-legal/ui` und `@os-legal/caml/react`.
- Zentrales Styling in `frontend/src/assets/configurations/osLegalStyles.ts`, `frontend/src/theme` und globaler CSS-Datei.
- Hauptnavigation in `frontend/src/assets/configurations/menus.ts` und `frontend/src/components/layout/NavMenu.tsx`.
- Kernarbeitsplatz fuer Dokumente in `frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx`.

## 3. Datenmodell-Befund

Wichtige vorhandene Modelle:

- `Corpus`: guter Kandidat fuer "Akte", "Mandat", "Matter" oder "Dossier".
- `CorpusFolder`, `DocumentPath`: vorhandene Struktur fuer Aktenordner.
- `Document`: zentrale Datei-/Text-/PDF-/DOCX-Einheit mit Extrakten, Summary, Versionierung, Hash und Verarbeitungsstatus.
- `Annotation`, `Relationship`, `CorpusReference`: Quellen, Fundstellen, Verweise und zitierbare Textstellen.
- `Extract`, `Fieldset`, `Column`, `Datacell`: strukturierte Ergebnisdaten, ideal fuer Vertragspruefungen.
- `Analysis`: Ergebnisrahmen fuer Analyzer/Prueflaeufe, noch parallel zu Extracts vorhanden.
- `Note` und `NoteRevision`: gut fuer erste Drafts, Bearbeitungshinweise und Review-Kommentare.
- `Conversation`, `ChatMessage`: persistenter Chat mit Dokumenten- und Corpus-Kontext.
- `AgentConfiguration`, `AgentActionResult`: konfigurierbare Kanzlei-Agenten und deren Ausfuehrungsergebnisse.
- `CorpusAction`, `CorpusActionExecution`: Workflow-/AI-Action-System mit Triggern, Status, Ergebnis- und Fehlertracking.
- `PipelineSettings`: zentrale Pipeline-/LLM-/Embedder-Konfiguration mit verschluesselten Secrets.

Mapping fuer die Kanzlei-Workspace:

- Akte/Mandat: zunaechst `Corpus`, spaeter optional eigenes `Matter`-Alias nur in UI/API.
- Vertragspruefung: `Extract`/`Datacell` plus Quellen-Annotationen.
- Review-Lauf: `CorpusActionExecution` oder `Analysis`.
- AI-Aktion: vorhandene `CorpusAction` plus `AgentActionResult`.
- Draft/Schriftsatz: MVP kann `Note` nutzen; fuer produktive Kanzlei-Workflows ist ein eigenes `Draft`-Modell sinnvoll.
- Playbook: MVP als Dokument/Note/Fieldset; spaeter eigenes versioniertes `Playbook`-Modell.

## 4. UI- und Design-Befund

Die technische UI-Basis ist brauchbar und bereits eher "SaaS/Workbench" als Marketing-Seite. Die wichtigsten Ankerpunkte:

- `NavMenu.tsx` und `menus.ts`: Branding und Informationsarchitektur.
- `App.tsx`: Routenstruktur.
- `DocumentKnowledgeBase.tsx`: zentrale Dokumentenarbeitsflaeche.
- `DesktopDocumentLayout.tsx`: Drei-Spalten-Arbeitsplatz mit Dokument, Werkzeugen und rechter Seitenleiste.
- `RightPanelContent.tsx`: Umschaltung zwischen Chat, Extracts, Analysis, Feed, Index, References und Discussions.
- `SidebarTabs.tsx`: natuerlicher Ort fuer neue Legal-AI-Tabs wie Review, Draft oder Aktionen.
- `ChatTray.tsx`: vorhandener dokumenten- und corpusbezogener KI-Chat mit Quellen und Tool-Freigaben.
- `CorpusSettings.tsx`, `CreateCorpusActionModal.tsx`, `RunCorpusActionModal.tsx`: bestehende UI fuer wiederholbare AI-Actions.

Aktueller Eindruck:

- Staerken: starke Dokumentenansicht, vorhandener Chat, viele Admin-/Workflow-Haken.
- Schwaechen: Begriffe wie Corpus, Extracts und Label Sets sind fuer Kanzleien zu technisch; Navigation ist nicht an Mandatsarbeit ausgerichtet; Discovery-/Community-Elemente wirken fuer eine Kanzlei-Workspace stoerend.
- Design-System: gute zentrale Token, aber fuer eine Kanzlei-Version sollte die Oberflaeche ruhiger, dichter und weniger produktdemohaft werden.

## 5. Zielarchitektur

Empfohlene Zielstruktur:

- Frontend bleibt React/Vite und wird nicht ersetzt.
- Backend bleibt Django/GraphQL/Celery.
- OpenContracts bleibt das System of Record fuer Dokumente, Akten, Annotationen, Extraktionen, Chats und Agenten.
- Legal-AI-Features werden als neue fachliche Schicht ueber bestehenden Modellen gebaut.
- LLM-Aufrufe laufen serverseitig ueber die vorhandene Provider-Registry.
- Externe Agenten- oder RAG-Systeme werden hoechstens im Hintergrund ueber MCP/API angebunden, nicht als eingebettete Haupt-UI.

Nicht empfohlen:

- Keine iframe-Loesung mit Dify, RAGFlow, AnythingLLM oder Open WebUI als sichtbare Hauptoberflaeche.
- Kein separater Dokumentenspeicher fuer AI-Tools.
- Kein frueher Vollumbau des Datenmodells.
- Kein Rich-Text-/Word-Klon im Browser als MVP.

## 6. Design- und Rebranding-Strategie

Erste UI-Umbenennungen:

- "Corpuses" zu "Akten" oder "Mandate".
- "Documents" zu "Dokumente".
- "Extracts" zu "Pruefergebnisse" oder "Auswertungen".
- "Analyses" zu "Prueflaeufe".
- "Label Sets" und technische Admin-Funktionen in Einstellungen/Admin verschieben.
- Neue Hauptpunkte: Akten, Dokumente, Vertragspruefung, Entwuerfe, Playbooks, Export.

Zentrale Dateien:

- `frontend/src/assets/configurations/menus.ts`
- `frontend/src/components/layout/NavMenu.tsx`
- `frontend/src/assets/configurations/osLegalStyles.ts`
- `frontend/src/theme/colors.ts`
- `frontend/src/theme/theme.ts`
- `frontend/src/index.css`
- `frontend/src/App.tsx`

Visueller Stil:

- Dichte, ruhige Arbeitsoberflaeche statt Landingpage-Optik.
- Maximal 8px Radius fuer Karten/Panels in der Kanzlei-Variante.
- Neutrale Flaechen, klare Kontraste, dezente Akzentfarbe.
- Risikohinweise mit konsistenten Farben fuer niedrig/mittel/hoch/kritisch.
- Keine dekorativen Illustrationen in der Produktoberflaeche.

## 7. MVP-Phasen

Phase 0: Rebrand und Navigation

- App-Name, Navigation und zentrale Begriffe auf Kanzlei-Workflows umstellen.
- Discovery-/Community-Flows aus der Hauptnavigation entfernen oder nachrangig machen.
- Dashboard fuer Akten/Dokumente als Startpunkt.

Phase 1: Akten- und Dokumenten-Workspace

- `Corpus` als Akte verwenden.
- Dokumentenarbeitsplatz beibehalten und rechte Seitenleiste fuer Legal-AI erweitern.
- Chat als "Fragen zum Dokument" sichtbar machen.
- Quellen/Annotationen als beweisbare Fundstellen betonen.

Phase 2: Vertragspruefung

- Erste AI-Aktion "Vertrag pruefen" als CorpusAction/AgentAction implementieren.
- Ergebnis als strukturierte Liste mit Risiko, Klausel, Fundstelle, Empfehlung.
- Quellen ueber Annotationen oder `Datacell.sources` verknuepfen.
- Ergebnis zunaechst im rechten Panel anzeigen, spaeter als Review-Bericht exportieren.

Phase 3: Drafting und Schriftsatz

- Einfacher Draft-Editor als Text/Markdown, kein Word-Klon.
- Drafts zuerst als `Note` speichern; bei echtem Produktbedarf eigenes `Draft`-Modell.
- LLM generiert Entwurf mit klaren Quellen und Nutzerbestaetigung.

Phase 4: DOCX-Export

- Backend-Service fuer DOCX aus Template plus Draft-Daten.
- Download ueber GraphQL-Mutation oder REST-Endpoint.
- Optional persistenter `ExportJob` fuer Nachvollziehbarkeit.

Phase 5: Playbooks

- Playbooks als wiederverwendbare Pruef-/Drafting-Vorgaben.
- Erste Version mit gespeicherten Prompts/Fieldsets/AgentConfigurations.
- Spaetere Versionierung, Freigabe und Kanzlei-Standardbibliothek.

## 8. Konkrete Implementierungspunkte

Frontend:

- Neue Routen in `frontend/src/App.tsx`: `/matters`, `/contract-review`, `/drafts`, `/playbooks`, `/exports`.
- Navigation in `menus.ts` und `NavMenu.tsx`.
- Neuer Legal-AI-Tab in `SidebarTabs.tsx`.
- Neues Panel in `RightPanelContent.tsx`, z.B. `legal_review`.
- Review-Komponenten nahe beim Dokumentenarbeitsplatz ablegen, z.B. `frontend/src/components/legal_ai/review`.
- Draft-Komponenten z.B. `frontend/src/components/legal_ai/drafts`.
- GraphQL-Dokumente in `frontend/src/graphql/queries.ts` und `frontend/src/graphql/mutations.ts` erweitern.

Backend:

- Zunaechst neue Mutationen in `config/graphql`, z.B. `RunLegalReview`, `GenerateDraft`, `ExportDraftDocx`.
- Vertragsreview als Service-Modul, z.B. `opencontractserver/legal_ai/review_service.py`.
- Drafting als Service-Modul, z.B. `opencontractserver/legal_ai/drafting_service.py`.
- DOCX-Export als Service-Modul, z.B. `opencontractserver/legal_ai/docx_export.py`.
- Bei groesseren Jobs Celery-Tasks nutzen statt synchroner HTTP-Anfragen.

## 9. LLM-Integration

Vorhanden:

- Provider fuer OpenAI, Anthropic, Google und Ollama.
- Model-Spec-Format wie `openai:gpt-4o` oder `ollama:llama3.3`.
- Fallback-Reihenfolge: explizites Modell, Agent-Konfiguration, Corpus-Konfiguration, PipelineSettings, Django-Settings.
- `PipelineSettings.default_llm`, `Corpus.preferred_llm`, `AgentConfiguration.preferred_llm`.
- Secrets werden serverseitig verwaltet und verschluesselt gespeichert.
- Dokumenten- und Corpus-Agenten koennen strukturierte Pydantic-Antworten liefern.
- Tool-Freigaben und Schreibrechte sind bereits im Agentenpfad angelegt.

Empfehlung:

- Kein LLM-Key im Frontend.
- Vertragspruefung ueber `agents.get_structured_response_and_sources_from_document`.
- Ergebnisse typisiert validieren, dann speichern.
- Temperatur niedrig fuer Review/Drafting.
- Lokale Modelle ueber Ollama als Option anbieten, aber pro Kanzlei sichtbar machen, welches Modell verwendet wird.
- Die vom Zielprodukt gewuenschten generischen ENV-Namen `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` sind im Code nicht als einheitliche Schicht erkennbar; besser ist ein kleiner Kompatibilitaets-Mapping-Layer auf die vorhandene Provider-Konfiguration, falls diese Namen extern gefordert sind.

## 10. DOCX-Export

Vorhanden:

- DOCX wird im Projekt bereits geparst/gerendert (`docxodus`, `docxodus_parser`, `docx_thumbnailer`).
- `python-docx` steht in den lokalen Requirements.
- Es gibt einen Corpus-Export mit `UserExport`, Celery-Tasks, Post-Processors und Export-Modals.

Bewertung:

- Der vorhandene Corpus-Export ist fuer Daten-/Annotationsarchive gedacht, nicht fuer anwaltliche Schriftsaetze.
- Fuer MVP sollte ein eigener "Draft zu DOCX"-Pfad entstehen.
- `python-docx` ist ausreichend fuer einfache Schriftsaetze.
- `docxtpl` waere besser fuer kanzleitypische Vorlagen mit Platzhaltern, ist aber noch nicht als Abhaengigkeit sichtbar.
- Pandoc waere maechtiger, bringt aber mehr Deployment-Komplexitaet.

Empfohlener MVP:

- Template-Datei serverseitig speichern.
- Draft-Daten und Metadaten in ein DOCX rendern.
- Datei als Download zurueckgeben.
- Optional erzeugtes DOCX als neues `Document` in der Akte speichern.
- Spaeter eigenes `DraftExport`/`ExportJob`-Modell fuer Status, Datei, Nutzer, Template-Version und Audit.

## 11. Playbooks

MVP-Variante:

- Playbook = strukturierte Kanzlei-Anweisung plus optionale Fieldsets/AgentConfiguration.
- Speicherung zunaechst mit bestehenden Modellen: `Fieldset`, `Column`, `AgentConfiguration`, `CorpusActionTemplate`, optional `Note` oder Dokument.
- Anwendung: Review-Aktion waehlt ein Playbook und erzeugt ein strukturiertes Ergebnis.

Spaetere Variante:

- Neues `Playbook`-Modell mit Feldern `name`, `description`, `document_type`, `jurisdiction`, `prompt`, `output_schema`, `version`, `status`, `created_by`, `approved_by`, `corpus_scope`.
- `PlaybookRun` oder Verknuepfung zu `CorpusActionExecution`.
- Freigabe-Workflow fuer Kanzlei-Standards.

## 12. Risiken und offene Punkte

Technische Risiken:

- Datenmodell kann schnell unklar werden, wenn Drafts, Notes, Analyses und Extracts vermischt werden.
- AI-Ergebnisse muessen nachvollziehbar, zitierbar und editierbar bleiben.
- DOCX-Vorlagen koennen je nach Kanzlei-Layout komplex werden.
- WebSocket-/Streaming-Chat und normale Action-Jobs brauchen klare UX-Grenzen.

Security/Compliance:

- Mandatsdaten duerfen nicht versehentlich an externe LLM-Provider gehen.
- Conversation- und LLM-Logs koennen sensible Daten enthalten.
- `Datacell.llm_call_log` und Tool-Ausfuehrungslogs sollten fuer Produktion minimiert, redigiert oder abschaltbar sein.
- Prompt-Injection durch Dokumentinhalte bleibt ein reales Risiko.
- Loesch-, Aufbewahrungs- und Audit-Policies muessen definiert werden.
- Bestehende Guardian-Berechtigungen sind ein starker Start, ersetzen aber keine Kanzlei-spezifischen Rollen und Mandantenisolation.

Lizenz:

- Das Hauptprojekt ist MIT-lizenziert.
- MIT ist fuer Forks und kommerzielle Nutzung grundsaetzlich freundlich, verlangt aber Beibehaltung von Copyright- und Lizenzhinweisen.
- Drittanbieter-Abhaengigkeiten muessen separat geprueft werden.
- Diese Bewertung ist technische Orientierung, keine Rechtsberatung.

Offen:

- Zielmarkt: interne Kanzlei-Installation oder mandantenfaehiges SaaS?
- Authentifizierung: lokaler Login, Auth0 oder Kanzlei-SSO?
- Datenstandort und LLM-Provider-Policy?
- Muss DOCX exakt Kanzlei-Templates entsprechen?
- Soll Drafting nur assistieren oder finale Dokumente erzeugen?

## 13. Naechste Schritte

1. Produktentscheidung treffen: "Akten-Workspace" statt allgemeine OpenContracts-Instanz.
2. UI-Begriffe und Navigation in einer kleinen PR umbauen.
3. Erste neue Route `/matters` als Alias/Wrapper fuer Corpuses bauen.
4. Rechten Dokumenten-Tab `legal_review` einfuegen.
5. Backend-Mutation `runLegalReview(documentId, corpusId, playbookId?)` entwerfen.
6. Ergebnis-Schema fuer Vertragspruefung als Pydantic-Modell definieren.
7. Ergebnis in `Extract`/`Datacell` mit Quellen speichern.
8. Draft-MVP als `Note`-basierte Textflaeche bauen.
9. DOCX-Export mit `python-docx` oder `docxtpl` prototypisieren.
10. Security-Review fuer Logs, Secrets, Provider-Auswahl und Berechtigungen vor produktiver Nutzung durchfuehren.
