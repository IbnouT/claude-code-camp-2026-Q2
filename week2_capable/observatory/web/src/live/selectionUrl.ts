const selectedRoomParameter = "room";

export function selectedRoomFromLocation(): string | null {
  return new URL(window.location.href).searchParams.get(selectedRoomParameter);
}

export function syncSelectedRoomToLocation(roomId: string | null): void {
  const url = new URL(window.location.href);
  if (roomId === null) {
    url.searchParams.delete(selectedRoomParameter);
  } else {
    url.searchParams.set(selectedRoomParameter, roomId);
  }
  window.history.replaceState(null, "", url);
}
