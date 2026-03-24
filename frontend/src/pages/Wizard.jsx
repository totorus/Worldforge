import { useParams } from "react-router-dom";

export default function Wizard() {
  const { sessionId } = useParams();
  return <div><h1>Wizard — {sessionId}</h1></div>;
}
