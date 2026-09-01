import React, { useState } from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@apollo/client";
import { userObj, authToken, authStatusVar } from "../graphql/cache";
import {
  LoginInputs,
  LoginOutputs,
  LOGIN_MUTATION,
} from "../graphql/mutations";
import { toast } from "react-toastify";
import { User, Lock } from "lucide-react";
import { CiteMark } from "../components/brand/CiteMark";
import { CiteWordmark } from "../components/brand/CiteWordmark";
import { useCacheManager } from "../hooks/useCacheManager";
import { saveLocalAuthSession } from "../utils/localAuthSession";
import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";

const PageWrapper = styled.div`
  width: 100vw;
  height: 100vh;
  background-image: url(/adam-rhodes-uBrWOHLgOcg-unsplash.jpg);
  background-size: cover;
  display: flex;
  justify-content: center;
  align-items: center;
`;

const LoginCard = styled.div`
  background-color: rgba(255, 255, 255, 0.9);
  border-radius: 10px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  padding: 2rem;
  width: 100%;
  max-width: 400px;
`;

const LogoSlot = styled.div`
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
`;

const WordmarkSlot = styled.div`
  display: flex;
  justify-content: center;
  margin-bottom: 0.5rem;
`;

const Subtitle = styled.p`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 0.875rem;
  color: #64748b;
  margin-bottom: 2rem;
`;

const Form = styled.form`
  display: flex;
  flex-direction: column;
`;

const InputWrapper = styled.div`
  position: relative;
  margin-bottom: 1rem;
`;

const Input = styled.input`
  width: 100%;
  padding: 0.75rem 1rem 0.75rem 2.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 1rem;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.accent};
  }
`;

const IconWrapper = styled.div`
  position: absolute;
  left: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  color: #666;
`;

const LoginButton = styled.button`
  background-color: ${OS_LEGAL_COLORS.ink};
  color: ${OS_LEGAL_COLORS.warmPaper};
  border: none;
  border-radius: 6px;
  padding: 0.75rem;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s ease;
  &:hover {
    background-color: ${OS_LEGAL_COLORS.inkHover};
  }
  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
`;

export const Login = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const { resetOnAuthChange } = useCacheManager();

  const [tryLogin, { loading: login_loading, error: login_error }] =
    useMutation<LoginOutputs, LoginInputs>(LOGIN_MUTATION, {
      onCompleted: async (data) => {
        // Clear the anonymous cache BEFORE flipping auth state. App.tsx's
        // GET_ME query is only skipped while authToken() is falsy (in local/
        // non-Auth0 deployments authInitCompleteVar is already true by the
        // time this fires), so setting authToken() first lets GET_ME start
        // fetching immediately and race with clearStore() below, which
        // cancels any in-flight query with an Apollo "store reset while
        // query was in flight" invariant violation (issue #2104). Awaiting
        // the reset first, then setting auth state, mirrors the ordering
        // AuthGate.tsx already uses to avoid the same race for Auth0 login.
        try {
          await resetOnAuthChange({
            reason: "user_login",
            refetchActive: false,
          });
        } catch (cacheError) {
          console.warn("[Login] Cache reset failed on login:", cacheError);
        }

        saveLocalAuthSession(data.tokenAuth.token, data.tokenAuth.user);
        authToken(data.tokenAuth.token);
        userObj(data.tokenAuth.user);
        authStatusVar("AUTHENTICATED");

        navigate("/");
      },
    });

  if (login_error) {
    toast.error("ERROR!\nCould not log you in!");
  }

  const handleLoginClick = (e: React.FormEvent) => {
    e.preventDefault();
    tryLogin({ variables: { username, password } });
  };

  return (
    <PageWrapper>
      <LoginCard>
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <LogoSlot>
            <CiteMark size={56} />
          </LogoSlot>
          <WordmarkSlot>
            <CiteWordmark size={32} ariaLabel="cite" />
          </WordmarkSlot>
          <Subtitle>Sign in to continue.</Subtitle>
        </div>
        <Form onSubmit={handleLoginClick}>
          <InputWrapper>
            <IconWrapper>
              <User size={18} />
            </IconWrapper>
            <Input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setUsername(e.target.value)
              }
            />
          </InputWrapper>
          <InputWrapper>
            <IconWrapper>
              <Lock size={18} />
            </IconWrapper>
            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setPassword(e.target.value)
              }
            />
          </InputWrapper>
          <LoginButton type="submit" disabled={login_loading}>
            {login_loading ? "Logging in..." : "Login"}
          </LoginButton>
        </Form>
      </LoginCard>
    </PageWrapper>
  );
};

export default Login;
