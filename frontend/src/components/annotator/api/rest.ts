import axios from "axios";
import { PageTokens } from "../../types";
import { expandPawlsPages } from "../../../utils/compactPawls";

export async function getPawlsLayer(url: string): Promise<PageTokens[]> {
  return axios.get(url).then((r) => expandPawlsPages(r.data));
}

export async function getDocumentRawText(url: string): Promise<string> {
  return axios.get(url).then((content) => content.data);
}
