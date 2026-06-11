import React from "react";
import { useQuery } from "@apollo/client";

import {
  GET_WANTED_AUTHORITIES,
  GetWantedAuthoritiesInputType,
  GetWantedAuthoritiesOutputType,
} from "../../../../graphql/queries";
import { WantedAuthoritiesCard } from "./WantedAuthoritiesCard";

/**
 * WantedAuthoritiesLive — fetches the corpus-scoped missing-authority backlog
 * and feeds the presentational ``WantedAuthoritiesCard``.
 *
 * Deliberately silent while loading, on error, and when the backlog is empty:
 * the card is a secondary "what to ingest next" hint below the governance
 * graph, so there is nothing useful to say in those states — flashing a
 * skeleton or an error card would give it more weight than it has.
 */
interface WantedAuthoritiesLiveProps {
  corpusId: string;
  testId?: string;
}

export const WantedAuthoritiesLive: React.FC<WantedAuthoritiesLiveProps> = ({
  corpusId,
  testId = "wanted-authorities",
}) => {
  const { data } = useQuery<
    GetWantedAuthoritiesOutputType,
    GetWantedAuthoritiesInputType
  >(GET_WANTED_AUTHORITIES, { variables: { corpusId } });

  const authorities = data?.wantedAuthorities;
  if (!authorities || authorities.length === 0) return null;

  return <WantedAuthoritiesCard authorities={authorities} testId={testId} />;
};
