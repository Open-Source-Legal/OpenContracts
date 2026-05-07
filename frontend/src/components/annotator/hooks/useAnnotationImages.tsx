import { useState, useEffect, useRef } from "react";
import { useReactiveVar } from "@apollo/client";
import { authToken } from "../../../graphql/cache";
import { getNumericIdFromGlobalId } from "../../../utils/idValidation";

interface ImageData {
  base64_data: string;
  format: string;
  data_url: string;
  page_index: number;
  token_index: number;
}

interface AnnotationImagesResponse {
  annotation_id: string;
  images: ImageData[];
  count: number;
}

interface UseAnnotationImagesResult {
  images: ImageData[] | null;
  loading: boolean;
  /** True only on a genuine fetch failure (5xx, network error, parse failure). */
  error: boolean;
  /** True after the request completed successfully but no images were returned. */
  hasFetchedEmpty: boolean;
}

// Simple in-memory cache for annotation images
const imageCache = new Map<string, ImageData[]>();

// HTTP statuses where the *absence* of a thumbnail is permanent for this
// annotation — safe to memoize as "empty" so we don't re-hit the endpoint.
//
// 404: no thumbnail row exists for this annotation; further fetches will
//      keep returning 404 until something writes an image, which would
//      invalidate the cache via a fresh page load anyway.
const CACHE_AS_EMPTY_STATUSES = new Set<number>([404]);

// HTTP statuses that should surface as "no thumbnail" without poisoning the
// cache: the next render with a different auth token (401/403) or after the
// throttle window (429) may legitimately succeed.
//
// 401/403: viewer lacks permission (or anonymous) — backend returns the same
//   empty-payload as missing/unauthorized for IDOR protection. Caching here
//   would prevent the re-fetch that should happen once the JWT loads.
// 429: throttled — the next request will likely succeed; never cache.
const TREAT_AS_EMPTY_NO_CACHE = new Set<number>([401, 403, 429]);

/**
 * Hook to fetch image data for an annotation from REST endpoint.
 * Only fetches if annotation has IMAGE content modality.
 * Results are cached to prevent duplicate requests.
 *
 * @param annotationId - The annotation ID (GraphQL relay format)
 * @param contentModalities - Array of modalities (TEXT, IMAGE, etc.)
 * @returns Object with images, loading state, error state, and an empty-success flag
 */
export const useAnnotationImages = (
  annotationId: string,
  contentModalities: string[] | undefined
): UseAnnotationImagesResult => {
  const [images, setImages] = useState<ImageData[] | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<boolean>(false);
  const [hasFetchedEmpty, setHasFetchedEmpty] = useState<boolean>(false);
  const token = useReactiveVar(authToken);

  // Track if we've already started fetching for this annotation
  const fetchedRef = useRef<string | null>(null);

  // Check for IMAGE modality - use stable check
  const hasImage = contentModalities?.includes("IMAGE") ?? false;

  useEffect(() => {
    // Reset if annotation changes
    if (fetchedRef.current !== annotationId) {
      fetchedRef.current = null;
    }

    // Only fetch if annotation has IMAGE modality
    if (!hasImage) {
      setImages(null);
      setLoading(false);
      setError(false);
      setHasFetchedEmpty(false);
      return;
    }

    // Extract numeric ID from relay ID
    let numericId: string;
    try {
      numericId = String(getNumericIdFromGlobalId(annotationId));
    } catch {
      setError(true);
      setHasFetchedEmpty(false);
      return;
    }

    // Check cache first
    const cached = imageCache.get(numericId);
    if (cached) {
      setImages(cached);
      setLoading(false);
      setError(false);
      setHasFetchedEmpty(cached.length === 0);
      return;
    }

    // Prevent duplicate fetches for same annotation
    if (fetchedRef.current === annotationId) {
      return;
    }
    fetchedRef.current = annotationId;

    const fetchImages = async () => {
      setLoading(true);
      setError(false);
      setHasFetchedEmpty(false);

      const url = `/api/annotations/${numericId}/images/`;

      try {
        const headers: HeadersInit = {
          "Content-Type": "application/json",
        };

        if (token) {
          headers["Authorization"] = `JWT ${token}`;
        }

        const response = await fetch(url, { headers });

        if (!response.ok) {
          if (CACHE_AS_EMPTY_STATUSES.has(response.status)) {
            // Permanent "no thumbnail" — safe to memoize.
            imageCache.set(numericId, []);
            setImages([]);
            setHasFetchedEmpty(true);
            return;
          }
          if (TREAT_AS_EMPTY_NO_CACHE.has(response.status)) {
            // Auth state may change or throttle may expire — show the
            // graceful placeholder but allow a retry on the next render.
            fetchedRef.current = null;
            setImages([]);
            setHasFetchedEmpty(true);
            return;
          }
          throw new Error(`HTTP ${response.status}`);
        }

        const data: AnnotationImagesResponse = await response.json();

        // Cache the result
        imageCache.set(numericId, data.images);
        setImages(data.images);
        setHasFetchedEmpty(data.images.length === 0);
      } catch (err) {
        console.error("[useAnnotationImages] Error:", err);
        setError(true);
        setImages(null);
        setHasFetchedEmpty(false);
        // Clear fetchedRef so retry is possible
        fetchedRef.current = null;
      } finally {
        setLoading(false);
      }
    };

    fetchImages();
  }, [annotationId, hasImage, token]);

  return { images, loading, error, hasFetchedEmpty };
};
