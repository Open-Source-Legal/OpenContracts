import axios from "axios";
import { CompactPage } from "../../types";
import { decodeV2Pawls } from "../../../utils/compactPawls";

export async function getPawlsLayer(url: string): Promise<CompactPage[]> {
  return axios.get(url).then((r) => {
    try {
      return decodeV2Pawls(r.data);
    } catch (err) {
      // Malformed PAWLs payloads (e.g. proxy error pages, mid-migration
      // documents written in an unrecognized shape) shouldn't crash the
      // document loading flow. Log for visibility and degrade to an empty
      // page list, matching the legacy expandPawlsPages behavior.
      console.error("Failed to decode PAWLs payload:", err);
      return [];
    }
  });
}

export async function getDocumentRawText(url: string): Promise<string> {
  return axios.get(url).then((content) => content.data);
}
