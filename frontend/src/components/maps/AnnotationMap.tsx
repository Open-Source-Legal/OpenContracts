import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import styled from "styled-components";
import { MapContainer, TileLayer, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet.markercluster";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";

// Leaflet's default marker icon paths break under bundlers (Leaflet computes
// image URLs relative to the CSS at runtime). Import the assets so the bundler
// fingerprints them, then pin them onto the default icon.
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

import {
  OS_LEGAL_COLORS,
  OS_LEGAL_SHADOWS,
  whiteAlpha,
} from "../../assets/configurations/osLegalStyles";
import {
  MAP_CLUSTER_MAX_RADIUS,
  MAP_DEFAULT_CENTER,
  MAP_DEFAULT_HEIGHT,
  MAP_DEFAULT_ZOOM,
  MAP_FIT_PADDING_PX,
  MAP_MAX_ZOOM,
  MAP_MIN_ZOOM,
  MAP_TILE_ATTRIBUTION,
  MAP_TILE_URL_TEMPLATE,
} from "../../assets/configurations/constants";
import { bandZoomRange, coarsestBand, labelTypeForZoom } from "./zoomBands";
import { AnnotationMapProps, GeographicAnnotationPin } from "./types";
import { pluralizeDocuments } from "../../utils/formatters";

// ---------------------------------------------------------------------------
// Leaflet default-icon fix (runs once at module load).
// ---------------------------------------------------------------------------
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

const prefersReducedMotion = (): boolean =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const samePin = (
  a: GeographicAnnotationPin,
  b: GeographicAnnotationPin
): boolean =>
  a.canonicalName === b.canonicalName &&
  a.labelType === b.labelType &&
  a.lat === b.lat &&
  a.lng === b.lng;

// ---------------------------------------------------------------------------
// Styled layout
// ---------------------------------------------------------------------------
const MapWrapper = styled.div<{ $height: string }>`
  position: relative;
  display: flex;
  width: 100%;
  height: ${(props) => props.$height};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: hidden;

  .leaflet-container {
    flex: 1 1 auto;
    height: 100%;
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }
`;

const LoadingOverlay = styled.div`
  position: absolute;
  top: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  padding: 0.35rem 0.85rem;
  border-radius: 999px;
  background: ${whiteAlpha(0.92)};
  box-shadow: ${OS_LEGAL_SHADOWS.floatingBadge};
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const SidePanel = styled.aside`
  flex: 0 0 280px;
  max-width: 280px;
  border-left: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surface};
  padding: 1rem;
  overflow-y: auto;
`;

const PanelTitle = styled.h3`
  margin: 0 0 0.25rem;
  font-size: 1rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const PanelMeta = styled.p`
  margin: 0 0 0.75rem;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const DocButton = styled.button`
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.4rem 0;
  border: none;
  background: none;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  cursor: pointer;

  &:hover,
  &:focus-visible {
    text-decoration: underline;
  }
`;

const ClosePanelButton = styled.button`
  margin-top: 0.5rem;
  padding: 0.35rem 0.75rem;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  background: none;
  font-size: 0.8125rem;
  cursor: pointer;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

// ---------------------------------------------------------------------------
// Internal child: imperative markercluster layer driven by react-leaflet's map.
// ---------------------------------------------------------------------------
interface ClusteredMarkersProps {
  pins: GeographicAnnotationPin[];
  onPinClick: (pin: GeographicAnnotationPin) => void;
}

const ClusteredMarkers: React.FC<ClusteredMarkersProps> = ({
  pins,
  onPinClick,
}) => {
  const map = useMap();
  const clusterGroupRef = useRef<L.MarkerClusterGroup | null>(null);
  // Keep the latest click handler without re-binding every marker.
  const onPinClickRef = useRef(onPinClick);
  onPinClickRef.current = onPinClick;

  // Create the cluster group once and attach it to the map.
  useEffect(() => {
    const animate = !prefersReducedMotion();
    const group = L.markerClusterGroup({
      maxClusterRadius: MAP_CLUSTER_MAX_RADIUS,
      animate,
      animateAddingMarkers: animate,
    });
    clusterGroupRef.current = group;
    map.addLayer(group);
    return () => {
      map.removeLayer(group);
      clusterGroupRef.current = null;
    };
  }, [map]);

  // Rebuild markers whenever the visible pin set changes.
  useEffect(() => {
    const group = clusterGroupRef.current;
    if (!group) {
      return;
    }
    group.clearLayers();
    pins.forEach((pin) => {
      const ariaLabel = `${pin.canonicalName}: ${pluralizeDocuments(
        pin.documentCount
      )}`;
      const marker = L.marker([pin.lat, pin.lng], {
        // ``keyboard`` makes the marker focusable; title/alt expose the label
        // to assistive tech.
        keyboard: true,
        title: ariaLabel,
        alt: ariaLabel,
      });
      const select = () => onPinClickRef.current(pin);
      marker.on("click", select);
      // ``keydown`` (not the deprecated ``keypress``) so Enter/Space activation
      // keeps working as browsers phase ``keypress`` out.
      marker.on("keydown", (event: L.LeafletKeyboardEvent) => {
        const key = event.originalEvent.key;
        if (key === "Enter" || key === " ") {
          event.originalEvent.preventDefault();
          select();
        }
      });
      group.addLayer(marker);
    });
  }, [pins]);

  return null;
};

// ---------------------------------------------------------------------------
// Internal child: relays Leaflet viewport changes to the parent.
// ---------------------------------------------------------------------------
interface ViewportReporterProps {
  onBoundsChange?: AnnotationMapProps["onBoundsChange"];
  onZoom: (zoom: number) => void;
}

const ViewportReporter: React.FC<ViewportReporterProps> = ({
  onBoundsChange,
  onZoom,
}) => {
  const report = (map: L.Map) => {
    onZoom(map.getZoom());
    if (!onBoundsChange) {
      return;
    }
    const b = map.getBounds();
    onBoundsChange(
      {
        south: b.getSouth(),
        west: b.getWest(),
        north: b.getNorth(),
        east: b.getEast(),
      },
      map.getZoom()
    );
  };

  useMapEvents({
    moveend: (event) => report(event.target as L.Map),
    zoomend: (event) => report(event.target as L.Map),
  });

  return null;
};

// ---------------------------------------------------------------------------
// Internal child: imperatively frames the map (auto-fit / deep-link focus).
//
// react-leaflet treats MapContainer `center`/`zoom` as mount-only, so framing
// an already-mounted map must go through the Leaflet instance (#1821). Both
// behaviours run at most once: auto-fit on the first non-empty pin set, focus
// once per distinct name (deferred until that pin actually loads).
// ---------------------------------------------------------------------------
interface MapControllerProps {
  pins: GeographicAnnotationPin[];
  fitToPins: boolean;
  focusPinName?: string | null;
  /** Selects a pin (opens the panel) and aligns the zoom band to it. */
  onFocus: (pin: GeographicAnnotationPin, zoom: number) => void;
}

const MapController: React.FC<MapControllerProps> = ({
  pins,
  fitToPins,
  focusPinName,
  onFocus,
}) => {
  const map = useMap();
  const didFitRef = useRef(false);
  const focusedNameRef = useRef<string | null>(null);

  // Deep-link focus: select + fly to the named pin once it appears.
  useEffect(() => {
    if (!focusPinName) {
      // Reset so a later re-set of the same name re-focuses.
      focusedNameRef.current = null;
      return;
    }
    if (focusedNameRef.current === focusPinName) {
      return;
    }
    const pin = pins.find((p) => p.canonicalName === focusPinName);
    if (!pin) {
      // Pins not loaded yet; this effect re-runs when `pins` arrive.
      return;
    }
    focusedNameRef.current = focusPinName;
    // A deep-link focus consumes the one-shot auto-fit: if the focus param is
    // later cleared, auto-fit must not retroactively fire on this instance.
    didFitRef.current = true;
    // Fly to a zoom inside the pin's band so its marker stays visible; aligning
    // the parent's band zoom first keeps the selection from being dropped.
    const targetZoom = bandZoomRange(pin.labelType)[1];
    onFocus(pin, targetZoom);
    map.flyTo([pin.lat, pin.lng], targetZoom);
  }, [pins, focusPinName, map, onFocus]);

  // Auto-fit: frame the coarsest band's pins once, on first load. A deep-link
  // focus takes precedence (skip the fit so it doesn't fight the flyTo).
  //
  // Ordering invariant: this effect must run AFTER the focus effect above.
  // React runs effects in definition order, and the focus effect sets
  // `didFitRef.current = true` when it consumes the one-shot fit — so the
  // `didFitRef.current` guard here reflects focus priority. Keep this effect
  // below the focus effect.
  useEffect(() => {
    if (!fitToPins || didFitRef.current || focusPinName || pins.length === 0) {
      return;
    }
    const band = coarsestBand(pins);
    if (!band) {
      return;
    }
    const bounds = L.latLngBounds(
      pins
        .filter((pin) => pin.labelType === band)
        .map((pin) => [pin.lat, pin.lng] as [number, number])
    );
    if (!bounds.isValid()) {
      return;
    }
    didFitRef.current = true;
    // Clamp the fitted zoom into the band's range: capping the max keeps a lone
    // pin from slamming to street level, and raising the floor stops a wide
    // spread from zooming out past where the band's pins disappear.
    const [bandMin, bandMax] = bandZoomRange(band);
    // Pad the fit so framed pins are not flush against the viewport edges.
    const fitZoom = Math.min(
      map.getBoundsZoom(
        bounds,
        false,
        L.point(MAP_FIT_PADDING_PX, MAP_FIT_PADDING_PX)
      ),
      bandMax
    );
    map.setView(bounds.getCenter(), Math.max(fitZoom, bandMin));
  }, [pins, fitToPins, focusPinName, map]);

  return null;
};

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------
/**
 * Reusable Leaflet map that visualises geographic document-annotation pins.
 *
 * The component is intentionally caller-agnostic: it knows nothing about
 * Discover or any specific corpus. Callers fetch pins (via whatever GraphQL
 * query they like) and feed them in; the map filters them to the current zoom
 * band, clusters them, and reports viewport changes through `onBoundsChange`
 * so the caller can refetch for the new bbox.
 *
 * NOTE: `center` and `zoom` are **mount-only**. react-leaflet's `MapContainer`
 * treats them as immutable initial props (it does not re-read them after the
 * first render), so changing them on an already-mounted instance is silently
 * ignored. To recentre/zoom an existing map (e.g. when reused on Corpus Home,
 * #1821), drive it imperatively with `useMap().flyTo(center, zoom)` from an
 * effect, or force a remount via a `key`.
 */
export const AnnotationMap: React.FC<AnnotationMapProps> = ({
  pins,
  loading = false,
  onBoundsChange,
  onPinClick,
  onSelectDocument,
  center = MAP_DEFAULT_CENTER as [number, number],
  zoom = MAP_DEFAULT_ZOOM,
  height = MAP_DEFAULT_HEIGHT,
  className,
  fitToPins = false,
  focusPinName,
}) => {
  const [currentZoom, setCurrentZoom] = useState<number>(zoom);
  const [selectedPin, setSelectedPin] =
    useState<GeographicAnnotationPin | null>(null);
  const reducedMotion = useMemo(prefersReducedMotion, []);

  // Show only the pins whose label type matches the current zoom band.
  const visiblePins = useMemo(() => {
    const band = labelTypeForZoom(currentZoom);
    return pins.filter((pin) => pin.labelType === band);
  }, [pins, currentZoom]);

  // Drop a stale selection if the selected pin is no longer visible.
  useEffect(() => {
    if (selectedPin && !visiblePins.some((pin) => samePin(pin, selectedPin))) {
      setSelectedPin(null);
    }
  }, [visiblePins, selectedPin]);

  const handlePinClick = (pin: GeographicAnnotationPin) => {
    setSelectedPin(pin);
    onPinClick?.(pin);
  };

  // Deep-link focus selects a pin and aligns the band zoom in the same render
  // so the "drop stale selection" effect above keeps the selection. Does NOT
  // fire onPinClick: the focus originated from the caller (the URL), so echoing
  // it back would be redundant.
  const handleFocusPin = useCallback(
    (pin: GeographicAnnotationPin, targetZoom: number) => {
      setCurrentZoom(targetZoom);
      setSelectedPin(pin);
    },
    []
  );

  return (
    <MapWrapper
      $height={height}
      className={className}
      role="region"
      aria-label="Map of geographic document annotations"
    >
      <MapContainer
        center={center}
        zoom={zoom}
        minZoom={MAP_MIN_ZOOM}
        maxZoom={MAP_MAX_ZOOM}
        scrollWheelZoom
        zoomAnimation={!reducedMotion}
        markerZoomAnimation={!reducedMotion}
        fadeAnimation={!reducedMotion}
        worldCopyJump
      >
        <TileLayer
          url={MAP_TILE_URL_TEMPLATE}
          attribution={MAP_TILE_ATTRIBUTION}
        />
        <ClusteredMarkers pins={visiblePins} onPinClick={handlePinClick} />
        <ViewportReporter
          onBoundsChange={onBoundsChange}
          onZoom={setCurrentZoom}
        />
        <MapController
          pins={pins}
          fitToPins={fitToPins}
          focusPinName={focusPinName}
          onFocus={handleFocusPin}
        />
      </MapContainer>

      {loading && (
        <LoadingOverlay role="status" aria-live="polite">
          Loading places…
        </LoadingOverlay>
      )}

      {selectedPin && (
        <SidePanel aria-label={`Details for ${selectedPin.canonicalName}`}>
          <PanelTitle>{selectedPin.canonicalName}</PanelTitle>
          <PanelMeta>{pluralizeDocuments(selectedPin.documentCount)}</PanelMeta>
          {onSelectDocument && selectedPin.sampleDocumentIds.length > 0 && (
            <nav aria-label="Sample documents">
              {selectedPin.sampleDocumentIds.map((docId, index) => (
                <DocButton
                  key={docId}
                  type="button"
                  onClick={() => onSelectDocument(docId)}
                >
                  Open document {index + 1}
                </DocButton>
              ))}
            </nav>
          )}
          <ClosePanelButton type="button" onClick={() => setSelectedPin(null)}>
            Close
          </ClosePanelButton>
        </SidePanel>
      )}
    </MapWrapper>
  );
};

export default AnnotationMap;
