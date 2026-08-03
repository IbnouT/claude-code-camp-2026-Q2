"use client"

import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"

function Modal(props: DialogPrimitive.Root.Props) {
  return <DialogPrimitive.Root {...props} />
}

function ModalTrigger(props: DialogPrimitive.Trigger.Props) {
  return <DialogPrimitive.Trigger {...props} />
}

function ModalPortal(props: DialogPrimitive.Portal.Props) {
  return <DialogPrimitive.Portal {...props} />
}

function ModalBackdrop(props: DialogPrimitive.Backdrop.Props) {
  return <DialogPrimitive.Backdrop {...props} />
}

function ModalPopup(props: DialogPrimitive.Popup.Props) {
  return <DialogPrimitive.Popup {...props} />
}

function ModalTitle(props: DialogPrimitive.Title.Props) {
  return <DialogPrimitive.Title {...props} />
}

function ModalDescription(props: DialogPrimitive.Description.Props) {
  return <DialogPrimitive.Description {...props} />
}

function ModalClose(props: DialogPrimitive.Close.Props) {
  return <DialogPrimitive.Close {...props} />
}

export {
  Modal,
  ModalBackdrop,
  ModalClose,
  ModalDescription,
  ModalPopup,
  ModalPortal,
  ModalTitle,
  ModalTrigger,
}
