import {Helmet} from "react-helmet";
import React from "react";

export function HelmetHeaders() {
  return (
    <Helmet>
      <meta charSet="utf-8"/>
      <meta name="viewport" content="initial-scale=1, width=device-width"/>
      <title>Mopidy Revelry</title>
    </Helmet>
  );
}
