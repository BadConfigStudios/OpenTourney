import { createBrowserRouter } from "react-router";
import { Layout } from "./Layout";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <div>Events</div> },
      { path: "events/new", element: <div>New Event</div> },
      { path: "events/:eventId", element: <div>Event Detail</div> },
      { path: "pods/:podId/pairings", element: <div>Pairings</div> },
      { path: "pods/:podId/report", element: <div>Report</div> },
    ],
  },
]);
