import { createBrowserRouter } from "react-router";
import { EventDetail } from "./EventDetail";
import { EventList } from "./EventList";
import { Layout } from "./Layout";
import { NewEvent } from "./NewEvent";
import { Organizations } from "./Organizations";
import { Pairings } from "./Pairings";
import { Report } from "./Report";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <EventList /> },
      { path: "organizations", element: <Organizations /> },
      { path: "events/new", element: <NewEvent /> },
      { path: "events/:eventId", element: <EventDetail /> },
      { path: "pods/:podId/pairings", element: <Pairings /> },
      { path: "pods/:podId/report", element: <Report /> },
    ],
  },
]);
