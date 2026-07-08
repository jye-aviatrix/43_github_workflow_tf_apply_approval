module "mc-spoke" {
  source  = "terraform-aviatrix-modules/mc-spoke/aviatrix"
  version = "1.7.1"

  account  = var.aviatrix_account
  region   = "East US"
  name     = "eus-spoke1"
  cloud    = "Azure"
  cidr     = "10.1.1.0/24"
  attached = false
}
