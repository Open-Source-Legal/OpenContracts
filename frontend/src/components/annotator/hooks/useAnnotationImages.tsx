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
  error: boolean;
}

// Simple in-memory cache for annotation images
const imageCache = new Map<string, ImageData[]>();

/**
 * Hook to fetch image data for an annotation from REST endpoint.
 * Only fetches if annotation has IMAGE content modality.
 * Results are cached to prevent duplicate requests.
 *
 * @param annotationId - The annotation ID (GraphQL relay format)
 * @param contentModalities - Array of modalities (TEXT, IMAGE, etc.)
 * @returns Object with images, loading state, and error state
 */
export const useAnnotationImages = (
  annotationId: string,
  contentModalities: string[] | undefined
): UseAnnotationImagesResult => {
  const [images, setImages] = useState<ImageData[] | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<boolean>(false);
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
      return;
    }

    // Extract numeric ID from relay ID
    let numericId: string;
    try {
      numericId = String(getNumericIdFromGlobalId(annotationId));
    } catch {
      setError(true);
      return;
    }

    // Check cache first
    const cached = imageCache.get(numericId);
    if (cached) {
      setImages(cached);
      setLoading(false);
      setError(false);
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

      const url = `/api/annotations/${numericId}/images/`;

      try {
        const headers: HeadersInit = {
          "Content-Type": "application/json",
        };

        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const response = await fetch(url, { headers });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data: AnnotationImagesResponse = await response.json();

        // Cache the result
        imageCache.set(numericId, data.images);
        setImages(data.images);
      } catch (err) {
        console.error("[useAnnotationImages] Error:", err);
        setError(true);
        setImages(null);
        // Clear fetchedRef so retry is possible
        fetchedRef.current = null;
      } finally {
        setLoading(false);
      }
    };

    fetchImages();
  }, [annotationId, hasImage, token]);

  return { images, loading, error };
};
