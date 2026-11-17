import { createContext, useContext } from "react";

/** A copy of the app that only shows: the phone page. Marks keep their look but do nothing, editing controls are left out. */
export const ReadOnlyContext = createContext(false);

export const useReadOnly = () => useContext(ReadOnlyContext);
