module "mc-spoke" {
  source  = "terraform-aviatrix-modules/mc-spoke/aviatrix"
  version = "1.7.1"

  account       = var.aviatrix_account
  region        = "us-east-1"
  name          = "ue1spoke1"
  cloud         = "AWS"
  cidr          = "10.1.1.0/24"
  attached      = true
  ha_gw         = false
  transit_gw    = module.mc-transit.transit_gateway.gw_name
  instance_size = "t3.small"
  tags          = { env = "prod" }
}

module "mc-transit" {
  source  = "terraform-aviatrix-modules/mc-transit/aviatrix"
  version = "2.6.0"

  account       = var.aviatrix_account
  region        = "us-east-1"
  name          = "ue1transit1"
  cloud         = "AWS"
  cidr          = "10.1.2.0/24"
  ha_gw         = false
  instance_size = "t3.small"
  tags          = { env = "prod" }
}
