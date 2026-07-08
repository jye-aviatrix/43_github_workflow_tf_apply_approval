variable "controller_password" {
  description = "Provide controller password"
  type        = string
  sensitive   = true
}

variable "controller_ip" {
  description = "Aviatrix controller IP or hostname"
  type        = string
}

variable "aviatrix_account" {
  description = "Aviatrix cloud access account name (as registered on the controller)"
  type        = string
}