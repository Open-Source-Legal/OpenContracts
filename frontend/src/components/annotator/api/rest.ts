import axios from "axios";
import { CompactPage } from "../../types";
import { decodeV2Pawls } from "../../../utils/compactPawls";

export async function getPawlsLayer(url: string): Promise<CompactPage[]> {
  return axios.get(url).then((r) => decodeV2Pawls(r.data));
}

export async function getDocumentRawText(url: string): Promise<string> {
  return axios.get(url).then((content) => content.data);
}
