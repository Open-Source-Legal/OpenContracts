import React from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { Button } from "@os-legal/ui";

export const NotFound: React.FC = () => {
  const navigate = useNavigate();
  return (
    <div style={{ padding: "3rem", textAlign: "center" }}>
      <AlertTriangle size={48} color="orange" />
      <h2 style={{ marginTop: "1rem" }}>404 — Not Found</h2>
      <p style={{ color: "#64748b" }}>
        The page you requested does not exist or the resource is not publicly
        accessible.
      </p>
      <Button variant="primary" onClick={() => navigate("/corpuses")}>
        Go to Corpuses
      </Button>
    </div>
  );
};

export default NotFound;
