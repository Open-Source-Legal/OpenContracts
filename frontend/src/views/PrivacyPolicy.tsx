import { Component } from "react";
import styled from "styled-components";

import { privacy_page_html } from "../assets/templates/privacy";

const Container = styled.div`
  max-width: 700px;
  margin: 5em auto 10em;
  padding: 0 1rem;
`;

export class PrivacyPolicy extends Component {
  render() {
    const template = { __html: privacy_page_html };

    return (
      <div>
        <Container>
          <div dangerouslySetInnerHTML={template} />
        </Container>
      </div>
    );
  }
}
