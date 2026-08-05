import { createBrowserRouter } from "react-router";
import { EventList } from "./EventList";
import { Layout } from "./Layout";
import { NewEvent } from "./NewEvent";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <EventList /> },
      { path: "events/new", element: <NewEvent /> },
      { path: "events/:eventId", element: <div>Event Detail</div> },
      { path: "pods/:podId/pairings", element: <div>Pairings</div> },
      { path: "pods/:podId/report", element: <div>Report</div> },
    ],
  },
]);
